"""
agentguard — Production-grade fault tolerance for AI agents.

Provides circuit breakers, LLM-aware retry, idempotency, loop detection,
and timeout enforcement for any AI agent or LLM pipeline.
"""

from .agent_wrapper import GuardedAgent, LoopDetector
from .circuit_breaker import CircuitBreaker, CircuitState
from .retry import LLMRetry, llm_retry
from .idempotency import IdempotentAgent, IdempotencyStore, make_idempotency_key
from .failure_classifier import FailureClassifier, FailureType
from .exceptions import (
    AgentGuardError,
    CircuitOpenError,
    MaxRetriesExceededError,
    IdempotencyError,
    AgentTimeoutError,
)

__version__ = "0.1.0"
__all__ = [
    "GuardedAgent",
    "LoopDetector",
    "CircuitBreaker",
    "CircuitState",
    "LLMRetry",
    "llm_retry",
    "IdempotentAgent",
    "IdempotencyStore",
    "make_idempotency_key",
    "FailureClassifier",
    "FailureType",
    "AgentGuardError",
    "CircuitOpenError",
    "MaxRetriesExceededError",
    "IdempotencyError",
    "AgentTimeoutError",
]
