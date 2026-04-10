import hashlib
import json
import time
import logging
from typing import Any, Optional, Dict, Callable
from .exceptions import IdempotencyError

logger = logging.getLogger(__name__)

class IdempotencyStore:
    """In-memory idempotency store. Replace with Redis/DB for production."""
    def __init__(self, ttl: float = 3600.0):
        self._store: Dict[str, Dict] = {}
        self.ttl = ttl

    def _cleanup(self):
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v["timestamp"] > self.ttl]
        for k in expired:
            del self._store[k]

    def get(self, key: str) -> Optional[Any]:
        self._cleanup()
        entry = self._store.get(key)
        if entry:
            logger.debug(f"Idempotency hit for key={key}")
            return entry["result"]
        return None

    def set(self, key: str, result: Any):
        self._store[key] = {"result": result, "timestamp": time.time()}
        logger.debug(f"Idempotency stored for key={key}")

    def clear(self, key: str):
        self._store.pop(key, None)

def make_idempotency_key(*args, **kwargs) -> str:
    payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()

class IdempotentAgent:
    def __init__(self, store: Optional[IdempotencyStore] = None, ttl: float = 3600.0):
        self.store = store or IdempotencyStore(ttl=ttl)

    def run(self, func: Callable, *args, idempotency_key: Optional[str] = None, **kwargs) -> Any:
        key = idempotency_key or make_idempotency_key(*args, **kwargs)
        cached = self.store.get(key)
        if cached is not None:
            logger.info(f"Returning cached result for idempotency key={key[:8]}...")
            return cached
        result = func(*args, **kwargs)
        self.store.set(key, result)
        return result
