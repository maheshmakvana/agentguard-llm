"""
agentguard — Production-grade fault tolerance for AI agents.

Provides circuit breakers, LLM-aware retry, idempotency, loop detection,
timeout enforcement, fallback chains, async support, health monitoring,
budget enforcement, and resilient batch execution for any AI agent or LLM pipeline.
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

# Advanced (0.2.0)
from .advanced import (
    ObservabilityHook,
    LoggingHook,
    GuardedAgentDecorator,
    guard,
    aguard,
    FallbackChain,
    AgentHealthMonitor,
    BudgetGuard,
    ResilientBatch,
)

__version__ = "0.2.0"
__all__ = [
    # Core
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
    # Advanced (0.2.0)
    "ObservabilityHook",
    "LoggingHook",
    "GuardedAgentDecorator",
    "guard",
    "aguard",
    "FallbackChain",
    "AgentHealthMonitor",
    "BudgetGuard",
    "ResilientBatch",
]
