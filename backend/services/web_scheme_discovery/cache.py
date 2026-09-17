"""Lightweight optional TTL cache (in-memory, stdlib only).

Caches discovery RESPONSES keyed by a hash of the normalized profile plus
query settings. Never stores secrets. Disabled when TTL <= 0.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 200):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _expired(self, expires_at: float) -> bool:
        return time.time() >= expires_at

    def get(self, key: str) -> Optional[Any]:
        if self.ttl_seconds <= 0:
            return None
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if self._expired(expires_at):
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl_seconds <= 0:
            return
        with self._lock:
            if len(self._store) >= self.max_entries:
                # Evict the oldest entry (simple FIFO by expiry).
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest, None)
            self._store[key] = (time.time() + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def profile_cache_key(profile: Dict[str, Any], extra: str = "") -> str:
    """Stable hash of a profile dict (keys sorted, PII kept server-side only)."""
    try:
        normalized = json.dumps(profile or {}, sort_keys=True, default=str)
    except Exception:
        normalized = str(profile)
    digest = hashlib.sha256((normalized + "|" + extra).encode("utf-8")).hexdigest()
    return digest


# Shared process-level cache instance (safe: responses only, no secrets).
_shared_cache = TTLCache()


def get_shared_cache(ttl_seconds: int | None = None) -> TTLCache:
    if ttl_seconds is not None and ttl_seconds != _shared_cache.ttl_seconds:
        _shared_cache.ttl_seconds = ttl_seconds
    return _shared_cache
