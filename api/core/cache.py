"""Simple in-memory TTL cache for expensive API queries."""

import time
import hashlib
import json
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}

# Default TTL: 5 minutes (data doesn't change intraday frequently)
DEFAULT_TTL = 300


def _make_key(prefix: str, params: dict | None) -> str:
    """Create a cache key from prefix + params."""
    raw = prefix + ":" + json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def get(prefix: str, params: dict | None = None) -> Any | None:
    """Get cached value if not expired."""
    key = _make_key(prefix, params)
    if key in _cache:
        expires_at, value = _cache[key]
        if time.time() < expires_at:
            return value
        del _cache[key]
    return None


def set(prefix: str, params: dict | None, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Store value in cache with TTL."""
    key = _make_key(prefix, params)
    _cache[key] = (time.time() + ttl, value)


def invalidate(prefix: str | None = None) -> None:
    """Invalidate cache entries. If prefix is None, clear all."""
    if prefix is None:
        _cache.clear()
        return
    keys_to_remove = [k for k in _cache if k.startswith(prefix)]
    for k in keys_to_remove:
        del _cache[k]
