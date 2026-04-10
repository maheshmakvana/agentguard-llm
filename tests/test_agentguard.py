import pytest
import time
from unittest.mock import MagicMock, patch
from agentguard import (
    GuardedAgent, CircuitBreaker, LLMRetry, IdempotentAgent,
    FailureClassifier, FailureType, CircuitOpenError, MaxRetriesExceededError
)
from agentguard.exceptions import AgentGuardError, AgentTimeoutError

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=999)
    def failing_func():
        raise RuntimeError("fail")
    for _ in range(3):
        try:
            cb.call(failing_func)
        except RuntimeError:
            pass
    with pytest.raises(CircuitOpenError):
        cb.call(failing_func)

def test_circuit_breaker_closes_on_success():
    cb = CircuitBreaker(failure_threshold=5)
    result = cb.call(lambda: 42)
    assert result == 42
    assert cb._failure_count == 0

def test_failure_classifier_rate_limit():
    fc = FailureClassifier()
    err = Exception("429 Too Many Requests rate limit exceeded")
    assert fc.classify(err) == FailureType.RATE_LIMIT
    assert fc.is_retryable(FailureType.RATE_LIMIT)

def test_failure_classifier_token_limit():
    fc = FailureClassifier()
    err = Exception("context length exceeded maximum context window")
    assert fc.classify(err) == FailureType.TOKEN_LIMIT
    assert not fc.is_retryable(FailureType.TOKEN_LIMIT)

def test_llm_retry_succeeds_on_second_attempt():
    call_count = [0]
    def flaky():
        call_count[0] += 1
        if call_count[0] < 2:
            raise Exception("503 service unavailable")
        return "success"
    retry = LLMRetry(max_attempts=3)
    with patch("agentguard.retry.time.sleep"):
        result = retry.execute(flaky)
    assert result == "success"
    assert call_count[0] == 2

def test_llm_retry_raises_after_max_attempts():
    def always_fail():
        raise Exception("503 service unavailable")
    retry = LLMRetry(max_attempts=2)
    with patch("agentguard.retry.time.sleep"):
        with pytest.raises(MaxRetriesExceededError):
            retry.execute(always_fail)

def test_idempotency_returns_cached():
    agent = IdempotentAgent()
    call_count = [0]
    def expensive():
        call_count[0] += 1
        return "result"
    r1 = agent.run(expensive, idempotency_key="key1")
    r2 = agent.run(expensive, idempotency_key="key1")
    assert r1 == r2 == "result"
    assert call_count[0] == 1

def test_guarded_agent_loop_detection():
    agent = GuardedAgent(name="test", max_repeated_actions=3, enable_idempotency=False)
    call_count = [0]
    def func():
        call_count[0] += 1
        return call_count[0]
    for _ in range(2):
        agent.run(func, action_label="search_web")
    with pytest.raises(AgentGuardError):
        agent.run(func, action_label="search_web")

def test_guarded_agent_timeout():
    agent = GuardedAgent(name="slow", timeout=0.1, enable_idempotency=False, max_retries=1)
    def slow_func():
        time.sleep(5)
        return "done"
    with pytest.raises((AgentTimeoutError, MaxRetriesExceededError)):
        agent.run(slow_func)

def test_guarded_agent_stats():
    agent = GuardedAgent(name="stats_test", enable_idempotency=False)
    agent.run(lambda: "ok")
    stats = agent.get_stats()
    assert stats["name"] == "stats_test"
    assert stats["total_calls"] == 1
    assert stats["total_failures"] == 0
