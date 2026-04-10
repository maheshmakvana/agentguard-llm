import re
from enum import Enum
from typing import Optional

class FailureType(Enum):
    RATE_LIMIT = "rate_limit"
    TOKEN_LIMIT = "token_limit"
    HALLUCINATED_TOOL_CALL = "hallucinated_tool_call"
    PROVIDER_OUTAGE = "provider_outage"
    INFINITE_LOOP = "infinite_loop"
    STATE_CORRUPTION = "state_corruption"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"

class FailureClassifier:
    RATE_LIMIT_PATTERNS = [
        r"rate.?limit", r"429", r"too many requests", r"quota exceeded",
        r"requests per minute", r"rpm", r"tpm"
    ]
    TOKEN_LIMIT_PATTERNS = [
        r"token.?limit", r"context.?length", r"maximum context",
        r"max_tokens", r"context window", r"input too long"
    ]
    PROVIDER_OUTAGE_PATTERNS = [
        r"500", r"502", r"503", r"service unavailable", r"internal server error",
        r"overloaded", r"capacity"
    ]
    HALLUCINATION_PATTERNS = [
        r"tool.?not.?found", r"function.?not.?exist", r"invalid.?tool",
        r"unknown.?function", r"no such tool"
    ]

    def classify(self, error: Exception) -> FailureType:
        msg = str(error).lower()
        for pattern in self.RATE_LIMIT_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return FailureType.RATE_LIMIT
        for pattern in self.TOKEN_LIMIT_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return FailureType.TOKEN_LIMIT
        for pattern in self.PROVIDER_OUTAGE_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return FailureType.PROVIDER_OUTAGE
        for pattern in self.HALLUCINATION_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return FailureType.HALLUCINATED_TOOL_CALL
        return FailureType.UNKNOWN

    def is_retryable(self, failure_type: FailureType) -> bool:
        return failure_type in {
            FailureType.RATE_LIMIT,
            FailureType.PROVIDER_OUTAGE,
            FailureType.TIMEOUT,
            FailureType.UNKNOWN
        }

    def get_retry_delay(self, failure_type: FailureType, attempt: int) -> float:
        if failure_type == FailureType.RATE_LIMIT:
            return min(60.0, 2 ** attempt * 5)
        if failure_type == FailureType.PROVIDER_OUTAGE:
            return min(120.0, 2 ** attempt * 10)
        return min(30.0, 2 ** attempt)
