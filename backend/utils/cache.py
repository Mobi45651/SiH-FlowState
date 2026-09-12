"""
utils/cache.py
----------------
A deliberately simple in-process TTL cache -- a plain dict guarded by a
lock, not Redis. For a single-process Flask dev server (which is what this
student project runs on) that's all that's needed; if you ever deploy with
multiple worker processes, each process will keep its own cache, which is
a documented limitation, not a bug. Swap this for Redis later if you need a
shared cache across processes -- the get/set interface below is deliberately
small so that swap wouldn't touch any calling code.

Connects to:
- services/weather_service.py -> wraps every Open-Meteo call with this
"""

import threading
import time
from typing import Any, Callable

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}  # key -> (expires_at_epoch, value)


def get(key: str) -> Any | None:
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() >= expires_at:
            del _store[key]
            return None
        return value


def set(key: str, value: Any, ttl_seconds: int) -> None:
    with _lock:
        _store[key] = (time.time() + ttl_seconds, value)


def get_or_set(key: str, ttl_seconds: int, compute_fn: Callable[[], Any]) -> Any:
    """Return the cached value if fresh, otherwise call compute_fn(), cache
    its result, and return that. compute_fn's exceptions propagate to the
    caller uncaught, so a failed fetch is never silently cached."""
    cached = get(key)
    if cached is not None:
        return cached
    value = compute_fn()
    set(key, value, ttl_seconds)
    return value


def clear() -> None:
    """Mainly for tests, so each test starts with a clean cache."""
    with _lock:
        _store.clear()
