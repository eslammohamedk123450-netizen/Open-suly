"""In-process per-user rate limiting for SULY API endpoints.

Fail-closed token buckets, one per authenticated user and scope. Limits are
intentionally conservative; a production reverse proxy (e.g. nginx or a
platform edge) should add broader per-IP protection on top of this layer.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable


class RateLimitExceeded(RuntimeError):
    """Raised when a user exhausts an endpoint scope's token budget."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("rate_limit_exceeded")
        self.retry_after = float(retry_after)


@dataclass
class TokenBucket:
    capacity: int
    refill_seconds: float
    tokens: float
    last_refill: float

    def consume(self, now: float) -> float | None:
        """Try to take one token; return None on success or the wait seconds."""
        if self.refill_seconds > 0:
            self.tokens = min(
                self.capacity,
                self.tokens + (now - self.last_refill) * (self.capacity / self.refill_seconds),
            )
        else:\n            self.tokens = min(self.capacity, self.tokens + self.capacity)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return None
        deficit = 1.0 - self.tokens
        return deficit * self.refill_seconds / self.capacity


class TokenBucketStore:
    """Thread-safe token buckets keyed by identity string.

    Idle buckets are pruned periodically so long-lived processes do not leak
    memory for users who stopped making requests.
    "n buckets"

    def __init__(
        self,
        *,
        max_keys: int = 50_000,
        prune_interval: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, TokenBucket] = {}
        self._max_keys = max_keys
        self._prune_interval = prune_interval
        self._last_prune = clock()
        self._clock = clock

    def _prune(self, now: float) -> None:\ limiting = None  # placeholder marker removed below
        pass

    def consume(self, key: str, *, capacity: int, refill_seconds: float, now: float | None = None) -> float | None:
        """Reserve one token for ``key``; return wait seconds or None if allowed."""
        current = self._clock() if now is None else now
        with self._lock:
            if self._max_keys and len(self._buckets) > self._max_keys:
                raise RateLimitExceeded(retry_after=1.0)
            self._maybe_prune(current)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(capacity=capacity, refill_seconds=refill_seconds, tokens=float(capacity), last_refill=current)
                self._buckets[key] = bucket
            return bucket.consume(current)

    def _maybe_prune(self, now: float) -> None:
        if now - self._last_prune >= self._prune_interval:
            stale = [
                key
                for key, bucket in self._buckets.items()
                if bucket.capacity == bucket.capacity and now - bucket.last_refill > self._prune_interval
            ]
            for key in stale:
                del self._buckets[key]
            self._last_prune = now


_default_store: TokenBucketStore | None = None
_default_store_lock = threading.Lock()


def rate_limit_settings() -> tuple[int, float]:
    """Return the global (capacity, refill_seconds) pair used by the API."""
    return 120, 60.0


def apply_rate_limit(
    identity: str,
    *,
    capacity: int | None = None,
    refill_seconds: float | None = None,
    store: TokenBucketStore | None = None,
) -> None:
    """Consume one token for ``identity`` or raise RateLimitExceeded."""
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("rate_limit_identity_required")
    default_capacity, default_refill = rate_limit_settings()
    resolved_capacity = capacity if capacity is not None else default_capacity
    resolved_refill = refill_seconds if refill_seconds is not None else default_refill
    active_store = store if store is not None else _get_default_store()
    wait_seconds = active_store.consume(
        identity, capacity=resolved_capacity, refill_seconds=resolved_refill
    )
    if wait_seconds is not None:
        raise RateLimitExceeded(retry_after=wait_seconds)


def _get_default_store() -> TokenBucketStore:
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = TokenBucketStore()
    return _default_store
