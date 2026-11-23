"""In-process, per-principal sliding-window rate limiting.

This limiter is defense in depth for each API process. It does not replace
ingress-level limits, DDoS protection, or provider-side quotas. Keys are
authenticated principal IDs, not client-supplied values.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings


class SlidingWindowLimiter:
    """Sliding window over monotonic timestamps, guarded by one lock."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        max_keys: int = 50_000,
        prune_interval: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("rate_limit_invalid")
        if (
            not isinstance(window_seconds, (int, float))
            or not math.isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("rate_limit_window_invalid")
        if isinstance(max_keys, bool) or not isinstance(max_keys, int) or max_keys < 0:
            raise ValueError("rate_limit_max_keys_invalid")
        if (
            not isinstance(prune_interval, (int, float))
            or not math.isfinite(prune_interval)
            or prune_interval <= 0
        ):
            raise ValueError("rate_limit_prune_interval_invalid")
        if not callable(clock):
            raise ValueError("rate_limit_clock_invalid")
        self._limit = limit
        self._window_seconds = float(window_seconds)
        self._max_keys = max_keys
        self._prune_interval = float(prune_interval)
        self._clock = clock
        self._last_prune = float(clock())
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        with self._lock:
            return self._limit

    def set_limit(self, limit: int) -> None:
        """Apply a changed server-side limit without clearing existing windows."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("rate_limit_invalid")
        with self._lock:
            self._limit = limit

    def _expire(self, events: deque[float], cutoff: float) -> None:
        while events and events[0] <= cutoff:
            events.popleft()

    def _maybe_prune(self, now: float) -> None:
        if now - self._last_prune < self._prune_interval:
            return
        cutoff = now - self._window_seconds
        stale = []
        for key, events in self._events.items():
            self._expire(events, cutoff)
            if not events:
                stale.append(key)
        for key in stale:
            del self._events[key]
        self._last_prune = max(self._last_prune, now)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        if not isinstance(key, str) or not key.strip() or len(key) > 512:
            raise ValueError("rate_limit_key_invalid")
        current = self._clock() if now is None else now
        if not isinstance(current, (int, float)) or not math.isfinite(current):
            raise ValueError("rate_limit_time_invalid")
        current = float(current)
        with self._lock:
            self._maybe_prune(current)
            if self._limit == 0:
                return False
            cutoff = current - self._window_seconds
            events = self._events.get(key)
            if events is None:
                if self._max_keys and len(self._events) >= self._max_keys:
                    # Do not evict a live principal to admit another identity.
                    return False
                events = deque()
                self._events[key] = events
            else:
                self._expire(events, cutoff)
            if len(events) >= self._limit:
                return False
            events.append(max(events[-1], current) if events and current < events[-1] else current)
            return True

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_prune = self._clock()


_limiters: dict[str, SlidingWindowLimiter] = {}
_limiters_lock = threading.Lock()


def get_limiter(scope: str, limit: int) -> SlidingWindowLimiter:
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("rate_limit_scope_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("rate_limit_disabled")
    with _limiters_lock:
        limiter = _limiters.get(scope)
        if limiter is None:
            limiter = SlidingWindowLimiter(limit)
            _limiters[scope] = limiter
        elif limiter.limit != limit:
            limiter.set_limit(limit)
        return limiter


def reset_limiters() -> None:
    """Test helper: forget all recorded events."""
    with _limiters_lock:
        _limiters.clear()


def rate_limit(scope: str) -> Callable[..., None]:
    """Return a dependency that enforces the configured per-user limit."""

    def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> None:
        settings = get_settings()
        limits = {
            "chat_respond": settings.rate_limit_chat_respond_per_minute,
            "chat_conversations": settings.rate_limit_chat_conversations_per_minute,
            "chat_messages": settings.rate_limit_chat_messages_per_minute,
            "chat_export": settings.rate_limit_chat_export_per_minute,
            "owner_ai_provider": getattr(settings, "rate_limit_owner_ai_provider_per_minute", 5),
        }
        if scope not in limits:
            raise ValueError("rate_limit_scope_unknown")
        limit = limits[scope]
        if limit <= 0:
            return
        if not get_limiter(scope, limit).allow(user.id):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait a moment and try again.",
            )

    return dependency
