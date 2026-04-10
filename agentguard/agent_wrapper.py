import time
import logging
import threading
from typing import Callable, Any, Optional, List, Dict
from .circuit_breaker import CircuitBreaker
from .retry import LLMRetry
from .idempotency import IdempotentAgent, IdempotencyStore
from .failure_classifier import FailureClassifier
from .exceptions import AgentTimeoutError, AgentGuardError

logger = logging.getLogger(__name__)

class LoopDetector:
    def __init__(self, max_repeated: int = 3, window: int = 10):
        self.max_repeated = max_repeated
        self.window = window
        self._history: List[str] = []

    def check(self, action: str) -> bool:
        self._history.append(action)
        if len(self._history) > self.window:
            self._history = self._history[-self.window:]
        recent = self._history[-self.max_repeated:]
        if len(recent) == self.max_repeated and len(set(recent)) == 1:
            logger.warning(f"Loop detected: action '{action}' repeated {self.max_repeated} times")
            return True
        return False

    def reset(self):
        self._history.clear()

class GuardedAgent:
    """
    Wraps any agent function with:
    - Circuit breaker (stops cascading failures)
    - LLM-aware retry (understands rate limits, token limits, etc.)
    - Idempotency (prevents duplicate executions)
    - Loop detection (stops infinite agent loops)
    - Timeout enforcement
    """
    def __init__(
        self,
        name: str = "agent",
        max_retries: int = 3,
        circuit_threshold: int = 5,
        circuit_recovery: float = 60.0,
        timeout: Optional[float] = None,
        loop_detection: bool = True,
        max_repeated_actions: int = 3,
        idempotency_ttl: float = 3600.0,
        enable_idempotency: bool = True,
    ):
        self.name = name
        self.timeout = timeout
        self.loop_detector = LoopDetector(max_repeated=max_repeated_actions) if loop_detection else None
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_threshold,
            recovery_timeout=circuit_recovery,
            name=name
        )
        self.retry = LLMRetry(max_attempts=max_retries, classifier=FailureClassifier())
        self.idempotent = IdempotentAgent(ttl=idempotency_ttl) if enable_idempotency else None
        self._call_count = 0
        self._failure_count = 0

    def run(
        self,
        func: Callable,
        *args,
        action_label: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        **kwargs
    ) -> Any:
        self._call_count += 1

        # Loop detection
        if self.loop_detector and action_label:
            if self.loop_detector.check(action_label):
                raise AgentGuardError(
                    f"Agent '{self.name}' detected infinite loop on action '{action_label}'"
                )

        def _execute():
            if self.idempotent and idempotency_key:
                return self.idempotent.run(
                    lambda: self.retry.execute(func, *args, **kwargs),
                    idempotency_key=idempotency_key
                )
            return self.retry.execute(func, *args, **kwargs)

        def _with_circuit():
            return self.circuit_breaker.call(_execute)

        if self.timeout:
            result_container = [None]
            error_container = [None]

            def _target():
                try:
                    result_container[0] = _with_circuit()
                except Exception as e:
                    error_container[0] = e

            thread = threading.Thread(target=_target)
            thread.start()
            thread.join(timeout=self.timeout)
            if thread.is_alive():
                self._failure_count += 1
                raise AgentTimeoutError(
                    f"Agent '{self.name}' timed out after {self.timeout}s"
                )
            if error_container[0]:
                self._failure_count += 1
                raise error_container[0]
            return result_container[0]
        else:
            try:
                return _with_circuit()
            except Exception:
                self._failure_count += 1
                raise

    def get_stats(self) -> Dict:
        return {
            "name": self.name,
            "total_calls": self._call_count,
            "total_failures": self._failure_count,
            "circuit": self.circuit_breaker.get_stats(),
        }

    def reset_loop_detector(self):
        if self.loop_detector:
            self.loop_detector.reset()
