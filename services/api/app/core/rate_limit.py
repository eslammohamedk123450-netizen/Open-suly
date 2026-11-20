"""In-process, per-principal sliding-window rate limiting.

This limiter is a defense-in-depth control inside each API process. It does not
replace ingress-level limits, DDoS protection, or provider-side quotas. Limits
are keyed by the authenticated user id and never by client-supplied data.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings


class SlidingWindowLimiter:
    """Sliding window over monotonic timestamps, guarded by one lock."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        if limit < 0:
            raise ValueError("rate_limit_invalid")
        self._limit = limit
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._events[key]
            cutoff = current - self._window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self._limit:
                return False
            events.append(current)
            return True

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


_limiters: dict[str, SlidingWindowLimiter] = {}
_limiters_lock = threading.Lock()


def get_limiter(scope: str, limit: int) -> SlidingWindowLimiter:
    if limit <= 0:
        raise ValueError("rate_limit_disabled")
    with _limiters_lock:
        limiter = _limiters.get(scope)
        if limiter is None:
            limiter = SlidingWindowLimiter(limit)
            _limiters[scope] = limiter
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
