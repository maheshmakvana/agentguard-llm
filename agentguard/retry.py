import time
import logging
import functools
from typing import Callable, Any, Optional, Type, Tuple
from .failure_classifier import FailureClassifier, FailureType
from .exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)

class LLMRetry:
    def __init__(
        self,
        max_attempts: int = 3,
        classifier: Optional[FailureClassifier] = None,
        on_retry: Optional[Callable] = None,
    ):
        self.max_attempts = max_attempts
        self.classifier = classifier or FailureClassifier()
        self.on_retry = on_retry

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                failure_type = self.classifier.classify(e)
                logger.warning(
                    f"Attempt {attempt}/{self.max_attempts} failed. "
                    f"FailureType={failure_type.value}. Error: {e}"
                )
                if not self.classifier.is_retryable(failure_type):
                    logger.error(f"Non-retryable failure ({failure_type.value}), aborting.")
                    raise
                if attempt < self.max_attempts:
                    delay = self.classifier.get_retry_delay(failure_type, attempt)
                    logger.info(f"Retrying in {delay:.1f}s...")
                    if self.on_retry:
                        self.on_retry(attempt, failure_type, e)
                    time.sleep(delay)
        raise MaxRetriesExceededError(
            f"Max attempts ({self.max_attempts}) exceeded. Last error: {last_error}"
        ) from last_error

def llm_retry(max_attempts: int = 3, classifier: Optional[FailureClassifier] = None):
    """Decorator for LLM-aware retry."""
    def decorator(func: Callable) -> Callable:
        retry = LLMRetry(max_attempts=max_attempts, classifier=classifier)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return retry.execute(func, *args, **kwargs)
        return wrapper
    return decorator
