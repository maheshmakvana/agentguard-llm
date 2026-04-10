"""
agentguard.advanced — Advanced agent reliability utilities.

New in 0.2.0:
- arun / aguarded_agent: Async-native GuardedAgent execution
- GuardedAgentDecorator: @guard decorator for agent functions
- FallbackChain: Try primary → fallback(s) with typed error routing
- AgentHealthMonitor: Aggregate health metrics across multiple GuardedAgents
- BudgetGuard: Token/cost budget enforcement with hard-stop
- ObservabilityHook: Pluggable hook system (on_call, on_success, on_failure)
- ResilientBatch: Run many tasks with per-task fault isolation
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .circuit_breaker import CircuitBreaker
from .retry import LLMRetry
from .failure_classifier import FailureClassifier, FailureType
from .exceptions import AgentGuardError, AgentTimeoutError, CircuitOpenError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ObservabilityHook
# ---------------------------------------------------------------------------

class ObservabilityHook:
    """
    Pluggable hook that fires on every agent call, success, and failure.

    Subclass and override any of the three methods, then pass the instance to
    GuardedAgentDecorator or FallbackChain.

    Example
    -------
    >>> class MyHook(ObservabilityHook):
    ...     def on_success(self, agent_name, result, elapsed):
    ...         print(f"{agent_name} OK in {elapsed:.2f}s")
    >>> @guard("my_agent", hooks=[MyHook()])
    ... def call_llm(prompt): ...
    """

    def on_call(self, agent_name: str, args: tuple, kwargs: dict) -> None:
        """Called before the agent function is invoked."""

    def on_success(self, agent_name: str, result: Any, elapsed: float) -> None:
        """Called when the agent call succeeds."""

    def on_failure(self, agent_name: str, error: Exception, elapsed: float) -> None:
        """Called when the agent call fails (after all retries)."""


class LoggingHook(ObservabilityHook):
    """Built-in hook that logs every call via the standard logging module."""

    def __init__(self, level: int = logging.INFO) -> None:
        self._level = level

    def on_call(self, agent_name: str, args: tuple, kwargs: dict) -> None:
        logger.log(self._level, "AGENT_CALL agent=%s", agent_name)

    def on_success(self, agent_name: str, result: Any, elapsed: float) -> None:
        logger.log(self._level, "AGENT_OK agent=%s elapsed=%.3fs", agent_name, elapsed)

    def on_failure(self, agent_name: str, error: Exception, elapsed: float) -> None:
        logger.warning("AGENT_FAIL agent=%s elapsed=%.3fs error=%s", agent_name, elapsed, error)


# ---------------------------------------------------------------------------
# GuardedAgentDecorator  (@guard / @aguard)
# ---------------------------------------------------------------------------

class GuardedAgentDecorator:
    """
    Decorator-based wrapper — guards a function with circuit breaker + retry.

    Parameters
    ----------
    name : str
        Agent identifier used in logs and metrics.
    max_retries : int
        Maximum retry attempts on retryable failures.
    circuit_threshold : int
        Failures before circuit opens.
    circuit_recovery : float
        Seconds before circuit transitions to HALF_OPEN.
    timeout : float | None
        Wall-clock timeout per call (seconds).
    hooks : list[ObservabilityHook]
        Zero or more hook instances.

    Example
    -------
    >>> dec = GuardedAgentDecorator("llm", max_retries=3, timeout=15.0)
    >>> @dec
    ... def call_llm(prompt: str) -> str: ...

    >>> # Or use the module-level shortcut:
    >>> @guard("llm", max_retries=3)
    ... def call_llm(prompt: str) -> str: ...
    """

    def __init__(
        self,
        name: str = "agent",
        *,
        max_retries: int = 3,
        circuit_threshold: int = 5,
        circuit_recovery: float = 60.0,
        timeout: Optional[float] = None,
        hooks: Optional[List[ObservabilityHook]] = None,
    ) -> None:
        self.name = name
        self.timeout = timeout
        self._hooks: List[ObservabilityHook] = hooks or []
        self._circuit = CircuitBreaker(
            failure_threshold=circuit_threshold,
            recovery_timeout=circuit_recovery,
            name=name,
        )
        self._retry = LLMRetry(max_attempts=max_retries, classifier=FailureClassifier())
        self._call_count = 0
        self._failure_count = 0

    # ---- sync __call__ ----

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self._run_sync(func, args, kwargs)
        wrapper.__guarded__ = self  # type: ignore[attr-defined]
        return wrapper

    def _run_sync(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        self._call_count += 1
        t0 = time.monotonic()
        for hook in self._hooks:
            hook.on_call(self.name, args, kwargs)

        def _execute():
            return self._retry.execute(func, *args, **kwargs)

        def _with_circuit():
            return self._circuit.call(_execute)

        try:
            if self.timeout:
                result_box: List[Any] = [None]
                err_box: List[Optional[Exception]] = [None]

                def _thread():
                    try:
                        result_box[0] = _with_circuit()
                    except Exception as exc:
                        err_box[0] = exc

                t = threading.Thread(target=_thread, daemon=True)
                t.start()
                t.join(timeout=self.timeout)
                if t.is_alive():
                    self._failure_count += 1
                    exc = AgentTimeoutError(f"Agent '{self.name}' timed out after {self.timeout}s")
                    elapsed = time.monotonic() - t0
                    for hook in self._hooks:
                        hook.on_failure(self.name, exc, elapsed)
                    raise exc
                if err_box[0]:
                    raise err_box[0]
                result = result_box[0]
            else:
                result = _with_circuit()

            elapsed = time.monotonic() - t0
            for hook in self._hooks:
                hook.on_success(self.name, result, elapsed)
            return result
        except Exception as exc:
            self._failure_count += 1
            elapsed = time.monotonic() - t0
            for hook in self._hooks:
                hook.on_failure(self.name, exc, elapsed)
            raise

    # ---- async support ----

    def async_call(self, func: Callable) -> Callable:
        """Wrap an async function."""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await self._run_async(func, args, kwargs)
        wrapper.__guarded__ = self  # type: ignore[attr-defined]
        return wrapper

    async def _run_async(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        self._call_count += 1
        t0 = time.monotonic()
        for hook in self._hooks:
            hook.on_call(self.name, args, kwargs)

        async def _execute():
            # Run sync retry in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._retry.execute(lambda: asyncio.run(func(*args, **kwargs)))
            )

        try:
            if self.timeout:
                result = await asyncio.wait_for(_execute(), timeout=self.timeout)
            else:
                result = await _execute()

            elapsed = time.monotonic() - t0
            for hook in self._hooks:
                hook.on_success(self.name, result, elapsed)
            return result
        except asyncio.TimeoutError:
            self._failure_count += 1
            exc = AgentTimeoutError(f"Agent '{self.name}' timed out after {self.timeout}s")
            elapsed = time.monotonic() - t0
            for hook in self._hooks:
                hook.on_failure(self.name, exc, elapsed)
            raise exc
        except Exception as exc:
            self._failure_count += 1
            elapsed = time.monotonic() - t0
            for hook in self._hooks:
                hook.on_failure(self.name, exc, elapsed)
            raise

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "total_calls": self._call_count,
            "total_failures": self._failure_count,
            "circuit": self._circuit.get_stats(),
        }


def guard(
    name: str = "agent",
    *,
    max_retries: int = 3,
    circuit_threshold: int = 5,
    circuit_recovery: float = 60.0,
    timeout: Optional[float] = None,
    hooks: Optional[List[ObservabilityHook]] = None,
) -> GuardedAgentDecorator:
    """
    Shortcut factory that returns a GuardedAgentDecorator.

    Example
    -------
    >>> @guard("llm", max_retries=3, timeout=15.0)
    ... def call_llm(prompt: str) -> str:
    ...     return openai_client.chat(prompt)
    """
    return GuardedAgentDecorator(
        name=name,
        max_retries=max_retries,
        circuit_threshold=circuit_threshold,
        circuit_recovery=circuit_recovery,
        timeout=timeout,
        hooks=hooks,
    )


def aguard(
    name: str = "agent",
    *,
    max_retries: int = 3,
    circuit_threshold: int = 5,
    circuit_recovery: float = 60.0,
    timeout: Optional[float] = None,
    hooks: Optional[List[ObservabilityHook]] = None,
) -> Callable:
    """
    Shortcut factory for guarding **async** agent functions.

    Example
    -------
    >>> @aguard("llm_async", timeout=20.0)
    ... async def call_llm_async(prompt: str) -> str: ...
    """
    dec = GuardedAgentDecorator(
        name=name,
        max_retries=max_retries,
        circuit_threshold=circuit_threshold,
        circuit_recovery=circuit_recovery,
        timeout=timeout,
        hooks=hooks,
    )
    return dec.async_call


# ---------------------------------------------------------------------------
# FallbackChain
# ---------------------------------------------------------------------------

class FallbackChain:
    """
    Try a primary agent function; on failure, try each fallback in order.

    Optionally route specific failure types to specific fallbacks.

    Parameters
    ----------
    primary : callable
        The main agent function to attempt first.
    fallbacks : list[callable]
        Ordered list of fallback callables.
    catch : tuple[type[Exception], ...]
        Exception types that trigger fallback (default: all exceptions).
    name : str
        Name used in logs.

    Example
    -------
    >>> chain = FallbackChain(
    ...     primary=call_gpt4,
    ...     fallbacks=[call_gpt35, call_local_llm],
    ...     name="llm_chain",
    ... )
    >>> result = chain.run("What is 2+2?")
    """

    def __init__(
        self,
        primary: Callable,
        fallbacks: List[Callable],
        *,
        catch: Tuple[Type[Exception], ...] = (Exception,),
        name: str = "fallback_chain",
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks
        self._catch = catch
        self.name = name
        self._attempts: List[Dict[str, Any]] = []

    def run(self, *args, **kwargs) -> Any:
        """Run primary, then fallbacks until one succeeds."""
        candidates = [self._primary] + list(self._fallbacks)
        last_error: Optional[Exception] = None

        for i, fn in enumerate(candidates):
            label = "primary" if i == 0 else f"fallback[{i}]"
            t0 = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                elapsed = time.monotonic() - t0
                logger.info("FallbackChain '%s': %s succeeded in %.3fs", self.name, label, elapsed)
                self._attempts.append({"label": label, "status": "ok", "elapsed": elapsed})
                return result
            except self._catch as exc:
                elapsed = time.monotonic() - t0
                logger.warning(
                    "FallbackChain '%s': %s failed in %.3fs — %s",
                    self.name, label, elapsed, exc
                )
                self._attempts.append({"label": label, "status": "fail", "elapsed": elapsed, "error": str(exc)})
                last_error = exc

        raise AgentGuardError(
            f"FallbackChain '{self.name}': all {len(candidates)} candidates failed. "
            f"Last error: {last_error}"
        ) from last_error

    async def arun(self, *args, **kwargs) -> Any:
        """Async version of run()."""
        candidates = [self._primary] + list(self._fallbacks)
        last_error: Optional[Exception] = None

        for i, fn in enumerate(candidates):
            label = "primary" if i == 0 else f"fallback[{i}]"
            t0 = time.monotonic()
            try:
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(*args, **kwargs)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
                elapsed = time.monotonic() - t0
                self._attempts.append({"label": label, "status": "ok", "elapsed": elapsed})
                return result
            except self._catch as exc:
                elapsed = time.monotonic() - t0
                self._attempts.append({"label": label, "status": "fail", "elapsed": elapsed, "error": str(exc)})
                last_error = exc

        raise AgentGuardError(
            f"FallbackChain '{self.name}': all {len(candidates)} candidates failed."
        ) from last_error

    @property
    def attempt_log(self) -> List[Dict[str, Any]]:
        """Return the history of all run attempts."""
        return list(self._attempts)


# ---------------------------------------------------------------------------
# AgentHealthMonitor
# ---------------------------------------------------------------------------

class AgentHealthMonitor:
    """
    Aggregate real-time health metrics across multiple GuardedAgent instances.

    Parameters
    ----------
    agents : list
        GuardedAgent (or GuardedAgentDecorator) instances to monitor.

    Example
    -------
    >>> monitor = AgentHealthMonitor([agent_a, agent_b])
    >>> print(monitor.report())
    """

    def __init__(self, agents: Optional[List[Any]] = None) -> None:
        self._agents: Dict[str, Any] = {}
        for ag in (agents or []):
            self.register(ag)

    def register(self, agent: Any) -> "AgentHealthMonitor":
        """Add a GuardedAgent or GuardedAgentDecorator to the monitor."""
        if not hasattr(agent, "get_stats"):
            raise TypeError(f"Agent {agent!r} does not implement get_stats()")
        name = agent.name if hasattr(agent, "name") else str(id(agent))
        self._agents[name] = agent
        return self

    def report(self) -> Dict[str, Any]:
        """Return a dict with per-agent and aggregate health stats."""
        per_agent = {}
        total_calls = 0
        total_failures = 0

        for name, ag in self._agents.items():
            stats = ag.get_stats()
            calls = stats.get("total_calls", 0)
            failures = stats.get("total_failures", 0)
            error_rate = round(failures / calls, 4) if calls else 0.0
            per_agent[name] = {
                **stats,
                "error_rate": error_rate,
                "healthy": stats.get("circuit", {}).get("state", "closed") != "open",
            }
            total_calls += calls
            total_failures += failures

        return {
            "agents": per_agent,
            "aggregate": {
                "total_calls": total_calls,
                "total_failures": total_failures,
                "overall_error_rate": round(total_failures / total_calls, 4) if total_calls else 0.0,
            },
        }

    def is_healthy(self) -> bool:
        """Return True if NO registered agent has an open circuit."""
        for ag in self._agents.values():
            stats = ag.get_stats()
            if stats.get("circuit", {}).get("state") == "open":
                return False
        return True


# ---------------------------------------------------------------------------
# BudgetGuard
# ---------------------------------------------------------------------------

class BudgetGuard:
    """
    Enforce a token or cost budget across multiple agent calls.

    Tracks cumulative token usage and raises BudgetExceededError when the
    limit is reached. Useful for hard-capping LLM spend in production.

    Parameters
    ----------
    max_tokens : int | None
        Hard token cap across all calls. None = no limit.
    max_cost : float | None
        Hard cost cap in USD. None = no limit.
    cost_per_token : float
        Estimated cost per token (default: $0.000002, approx GPT-3.5).

    Example
    -------
    >>> budget = BudgetGuard(max_tokens=50_000, max_cost=0.10)
    >>> @budget.wrap
    ... def call_llm(prompt, token_count=0): ...
    """

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        max_cost: Optional[float] = None,
        cost_per_token: float = 0.000002,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.cost_per_token = cost_per_token
        self._used_tokens: int = 0
        self._used_cost: float = 0.0
        self._lock = threading.Lock()

    def record(self, tokens: int) -> None:
        """Manually record token usage. Raises BudgetExceededError if over limit."""
        with self._lock:
            self._used_tokens += tokens
            self._used_cost += tokens * self.cost_per_token
            if self.max_tokens and self._used_tokens > self.max_tokens:
                raise AgentGuardError(
                    f"BudgetGuard: token budget exceeded "
                    f"({self._used_tokens} > {self.max_tokens})"
                )
            if self.max_cost and self._used_cost > self.max_cost:
                raise AgentGuardError(
                    f"BudgetGuard: cost budget exceeded "
                    f"(${self._used_cost:.4f} > ${self.max_cost:.4f})"
                )

    def wrap(self, func: Callable) -> Callable:
        """
        Decorator — calls func, then records `token_count` kwarg if present.

        The decorated function should accept a `token_count` keyword arg
        indicating how many tokens the call consumed.
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            tokens = kwargs.get("token_count", 0)
            if tokens:
                self.record(tokens)
            return result
        return wrapper

    @property
    def usage(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "used_tokens": self._used_tokens,
                "used_cost_usd": round(self._used_cost, 6),
                "remaining_tokens": (self.max_tokens - self._used_tokens) if self.max_tokens else None,
                "remaining_cost_usd": (
                    round(self.max_cost - self._used_cost, 6) if self.max_cost else None
                ),
            }

    def reset(self) -> None:
        with self._lock:
            self._used_tokens = 0
            self._used_cost = 0.0


# ---------------------------------------------------------------------------
# ResilientBatch
# ---------------------------------------------------------------------------

class ResilientBatch:
    """
    Run a list of tasks with per-task fault isolation using a thread pool.

    Unlike a plain ThreadPoolExecutor, failures in one task do NOT cancel
    other tasks. Each result is wrapped in a TaskResult.

    Parameters
    ----------
    max_workers : int
        Thread pool size.

    Example
    -------
    >>> batch = ResilientBatch(max_workers=8)
    >>> results = batch.run(call_llm, ["prompt1", "prompt2", "prompt3"])
    >>> for r in results:
    ...     if r.succeeded: print(r.value)
    ...     else: print("Failed:", r.error)
    """

    class TaskResult:
        __slots__ = ("index", "succeeded", "value", "error", "elapsed")

        def __init__(self, index: int, succeeded: bool, value: Any, error: Optional[Exception], elapsed: float):
            self.index = index
            self.succeeded = succeeded
            self.value = value
            self.error = error
            self.elapsed = elapsed

        def __repr__(self):
            if self.succeeded:
                return f"TaskResult(index={self.index}, ok, elapsed={self.elapsed:.3f}s)"
            return f"TaskResult(index={self.index}, FAIL={self.error!r}, elapsed={self.elapsed:.3f}s)"

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def run(
        self,
        func: Callable,
        items: List[Any],
        *,
        extra_args: tuple = (),
        extra_kwargs: Optional[Dict] = None,
    ) -> "List[ResilientBatch.TaskResult]":
        """
        Apply *func* to each item in *items* concurrently.

        Parameters
        ----------
        func : callable
            Called as func(item, *extra_args, **extra_kwargs).
        items : list
            Input items.
        """
        import concurrent.futures

        kw = extra_kwargs or {}
        results: List[ResilientBatch.TaskResult] = [None] * len(items)  # type: ignore

        def _run_one(idx: int, item: Any) -> "ResilientBatch.TaskResult":
            t0 = time.monotonic()
            try:
                val = func(item, *extra_args, **kw)
                return ResilientBatch.TaskResult(idx, True, val, None, time.monotonic() - t0)
            except Exception as exc:
                logger.warning("ResilientBatch task[%d] failed: %s", idx, exc)
                return ResilientBatch.TaskResult(idx, False, None, exc, time.monotonic() - t0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(_run_one, i, item): i for i, item in enumerate(items)}
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result()
                results[res.index] = res

        return results
