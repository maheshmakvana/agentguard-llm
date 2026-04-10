# agentguard — Production-Grade Fault Tolerance for AI Agents

[![PyPI version](https://badge.fury.io/py/agentguard.svg)](https://pypi.org/project/agentguard/)
[![Python Versions](https://img.shields.io/pypi/pyversions/agentguard.svg)](https://pypi.org/project/agentguard/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**agentguard** is a production-ready Python library that adds circuit breakers, LLM-aware retry logic, idempotency, loop detection, and timeout enforcement to any AI agent or LLM pipeline.

> AI agents fail at 91%+ rates in production. agentguard stops that.

---

## The Problem

AI agents built with LangChain, AutoGen, CrewAI, or custom LLM pipelines fail catastrophically in production due to:

- **Infinite loops** — agents repeat the same tool calls indefinitely
- **Silent failures** — LLM errors swallowed without retry or alerting
- **Duplicate actions** — the same expensive LLM call fires multiple times
- **Rate limit crashes** — no intelligent backoff for 429/503 errors
- **Token limit blindness** — agents don't know when to stop or summarize
- **No circuit breaking** — one bad model call cascades into total failure

Existing tools like `tenacity`, LangGraph, and CrewAI are not LLM-aware and don't address agent-specific failure modes.

---

## Features

- **Circuit Breaker** — Automatically opens after N failures, protecting downstream LLM APIs from cascading overload
- **LLM-Aware Retry** — Classifies errors (rate limit, token limit, provider outage, hallucinated tool call) and applies appropriate backoff
- **Idempotency** — Caches results by key to prevent duplicate expensive LLM executions
- **Loop Detection** — Detects and halts infinite agent action loops before they run up your API bill
- **Timeout Enforcement** — Hard timeouts on any agent step, with clean error propagation
- **Zero Dependencies** — Pure Python standard library only; works with any LLM framework
- **Full Observability** — Built-in stats, logging at every layer, structured error types

---

## Installation

```bash
pip install agentguard
```

---

## Quick Start

### GuardedAgent — Full Protection in One Wrapper

```python
from agentguard import GuardedAgent

agent = GuardedAgent(
    name="my_llm_agent",
    max_retries=3,
    circuit_threshold=5,
    timeout=30.0,
    loop_detection=True,
    max_repeated_actions=3,
)

def call_llm(prompt: str) -> str:
    # Your actual LLM call here (OpenAI, Anthropic, etc.)
    return f"Response to: {prompt}"

result = agent.run(call_llm, "What is the capital of France?", action_label="llm_call")
print(result)
print(agent.get_stats())
# {'name': 'my_llm_agent', 'total_calls': 1, 'total_failures': 0, 'circuit': {...}}
```

### Circuit Breaker — Standalone

```python
from agentguard import CircuitBreaker

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0, name="openai")

try:
    response = cb.call(call_llm, "Hello")
except Exception as e:
    print(f"Protected from cascading failure: {e}")

print(cb.get_stats())
# {'name': 'openai', 'state': 'closed', 'failure_count': 0, ...}
```

### LLM-Aware Retry — Decorator Style

```python
from agentguard import llm_retry

@llm_retry(max_attempts=3)
def my_agent_step(query: str) -> str:
    # Automatically retries on rate limits (429), provider outages (503)
    # Stops immediately on token limit errors (non-retryable)
    return call_llm(query)

result = my_agent_step("Summarize this document")
```

### LLM-Aware Retry — Programmatic

```python
from agentguard import LLMRetry, FailureClassifier

retry = LLMRetry(max_attempts=5, on_retry=lambda attempt, ftype, err: print(f"Retry {attempt}: {ftype}"))
result = retry.execute(call_llm, "Hello")
```

### Idempotency — Prevent Duplicate Executions

```python
from agentguard import IdempotentAgent

agent = IdempotentAgent(ttl=3600.0)

# First call executes the function
result1 = agent.run(call_llm, "Summarize report", idempotency_key="report-summary-v1")

# Second call with same key returns cached result instantly
result2 = agent.run(call_llm, "Summarize report", idempotency_key="report-summary-v1")

assert result1 == result2  # True — function only ran once
```

### Failure Classifier — Understand What Went Wrong

```python
from agentguard import FailureClassifier, FailureType

fc = FailureClassifier()

err = Exception("429 Too Many Requests: rate limit exceeded")
ftype = fc.classify(err)
# FailureType.RATE_LIMIT

print(fc.is_retryable(ftype))       # True
print(fc.get_retry_delay(ftype, attempt=1))  # 10.0 seconds
```

---

## Architecture

```
agentguard/
├── agent_wrapper.py      # GuardedAgent — orchestrates all protections
├── circuit_breaker.py    # CircuitBreaker — CLOSED/OPEN/HALF_OPEN state machine
├── retry.py              # LLMRetry + llm_retry decorator — intelligent backoff
├── idempotency.py        # IdempotentAgent + IdempotencyStore — result caching
├── failure_classifier.py # FailureClassifier — LLM error pattern recognition
└── exceptions.py         # Typed exception hierarchy
```

### Data Flow

```
Agent call
    │
    ├─► Loop Detector (infinite loop check)
    │
    ├─► Circuit Breaker (OPEN? → reject immediately)
    │
    ├─► Idempotency Store (seen this key? → return cached)
    │
    ├─► LLM Retry (classify failure → smart backoff → retry)
    │
    └─► Timeout Thread (hard deadline enforcement)
```

### Failure Classification Logic

| Error Pattern | Classified As | Retryable | Backoff |
|---|---|---|---|
| `429`, `rate limit`, `quota exceeded` | RATE_LIMIT | Yes | Exponential (5s base, max 60s) |
| `503`, `service unavailable`, `overloaded` | PROVIDER_OUTAGE | Yes | Exponential (10s base, max 120s) |
| `context length`, `token limit` | TOKEN_LIMIT | No | — |
| `tool not found`, `invalid tool` | HALLUCINATED_TOOL_CALL | No | — |
| anything else | UNKNOWN | Yes | Exponential (1s base, max 30s) |

---

## API Reference

### `GuardedAgent`

```python
GuardedAgent(
    name: str = "agent",
    max_retries: int = 3,
    circuit_threshold: int = 5,
    circuit_recovery: float = 60.0,
    timeout: Optional[float] = None,
    loop_detection: bool = True,
    max_repeated_actions: int = 3,
    idempotency_ttl: float = 3600.0,
    enable_idempotency: bool = True,
)
```

**Methods:**
- `run(func, *args, action_label=None, idempotency_key=None, **kwargs)` — Execute with all protections
- `get_stats()` — Returns dict with call counts, failure counts, circuit state
- `reset_loop_detector()` — Clear the loop detection history

### `CircuitBreaker`

```python
CircuitBreaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 1,
    name: str = "default"
)
```

**Methods:**
- `call(func, *args, **kwargs)` — Protected function call
- `get_stats()` — Returns state, failure count, last failure time

### `LLMRetry`

```python
LLMRetry(
    max_attempts: int = 3,
    classifier: Optional[FailureClassifier] = None,
    on_retry: Optional[Callable] = None,
)
```

**Methods:**
- `execute(func, *args, **kwargs)` — Execute with retry logic

### `llm_retry` decorator

```python
@llm_retry(max_attempts=3, classifier=None)
def my_func(): ...
```

### `IdempotentAgent`

```python
IdempotentAgent(store=None, ttl=3600.0)
```

**Methods:**
- `run(func, *args, idempotency_key=None, **kwargs)` — Execute with deduplication

### `FailureClassifier`

**Methods:**
- `classify(error: Exception) -> FailureType`
- `is_retryable(failure_type: FailureType) -> bool`
- `get_retry_delay(failure_type: FailureType, attempt: int) -> float`

### Exceptions

| Exception | When Raised |
|---|---|
| `AgentGuardError` | Base class for all agentguard errors |
| `CircuitOpenError` | Circuit breaker is OPEN, call rejected |
| `MaxRetriesExceededError` | All retry attempts exhausted |
| `IdempotencyError` | Idempotency store conflict |
| `AgentTimeoutError` | Agent exceeded timeout limit |

---

## Real-World Integration Examples

### With OpenAI

```python
import openai
from agentguard import GuardedAgent

agent = GuardedAgent(name="openai-agent", max_retries=3, timeout=30.0)

def gpt_call(prompt: str) -> str:
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

result = agent.run(gpt_call, "Explain quantum computing", action_label="gpt_call")
```

### With LangChain

```python
from agentguard import llm_retry

@llm_retry(max_attempts=3)
def run_chain(input_text: str):
    return my_langchain_chain.invoke({"input": input_text})
```

### With CrewAI / AutoGen

```python
from agentguard import GuardedAgent

guard = GuardedAgent(name="crew-agent", loop_detection=True, max_repeated_actions=5)

# Wrap any crew task execution
result = guard.run(crew.kickoff, action_label="crew_task")
```

---

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/your-feature`)
3. Run tests: `pytest tests/ -v`
4. Submit a pull request

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Links

- **PyPI**: https://pypi.org/project/agentguard/
- **GitHub**: https://github.com/agentguard-ai/agentguard
- **Issues**: https://github.com/agentguard-ai/agentguard/issues
