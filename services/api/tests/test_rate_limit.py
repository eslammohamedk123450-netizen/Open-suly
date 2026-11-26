from types import SimpleNamespace
import pytest

from fastapi.testclient import TestClient

from app.core import rate_limit as rate_limit_module
from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import chat as chat_module

client = TestClient(app)


_RESPOND_BODY = {
    "conversation_id": "00000000-0000-0000-0000-000000000001",
    "message_id": "00000000-0000-0000-0000-000000000002",
}


def _override_settings(monkeypatch, respond: int, conversations: int, messages: int) -> None:
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_chat_respond_per_minute=respond,
            rate_limit_chat_conversations_per_minute=conversations,
            rate_limit_chat_messages_per_minute=messages,
            rate_limit_chat_export_per_minute=2,
        ),
    )


def test_sliding_window_limiter_blocks_within_window_and_recovers() -> None:
    limiter = rate_limit_module.SlidingWindowLimiter(limit=2, window_seconds=60.0)
    assert limiter.allow("user-a", now=100.0)
    assert limiter.allow("user-a", now=100.5)
    assert not limiter.allow("user-a", now=101.0)
    # Independent principals never share a window.
    assert limiter.allow("user-b", now=101.0)
    # The oldest event ages out of the window and the limit frees up.
    assert limiter.allow("user-a", now=161.0)


def test_chat_respond_returns_429_after_configured_limit(monkeypatch) -> None:
    rate_limit_module.reset_limiters()
    _override_settings(monkeypatch, respond=2, conversations=10, messages=30)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="rate-user", email=None)
    try:
        statuses = [
            client.post("/v1/chat/respond", json=_RESPOND_BODY).status_code
            for _ in range(3)
        ]
    finally:
        app.dependency_overrides.clear()
        rate_limit_module.reset_limiters()
    # The first two requests pass the limiter and fail later at the unconfigured
    # server secret (503); the third is rejected by the limiter itself (429).
    assert statuses == [503, 503, 429]


def test_rate_limit_zero_disables_the_limiter(monkeypatch) -> None:
    rate_limit_module.reset_limiters()
    _override_settings(monkeypatch, respond=0, conversations=10, messages=30)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="rate-user", email=None)
    try:
        statuses = [
            client.post("/v1/chat/respond", json=_RESPOND_BODY).status_code
            for _ in range(4)
        ]
    finally:
        app.dependency_overrides.clear()
        rate_limit_module.reset_limiters()
    assert statuses == [503, 503, 503, 503]


@pytest.mark.parametrize(
    "route,body,scope",
    [
        ("/v1/chat/conversations", {"title": "Test"}, "conversations"),
        (
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000001/messages",
            {"content": "Hello"},
            "messages",
        ),
    ],
)
def test_chat_write_routes_enforce_independent_scopes(monkeypatch, route, body, scope):
    rate_limit_module.reset_limiters()
    limits = {"respond": 10, "conversations": 1, "messages": 1}
    limits[scope] = 1
    monkeypatch.setattr(
        rate_limit_module,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_chat_respond_per_minute=limits["respond"],
            rate_limit_chat_conversations_per_minute=limits["conversations"],
            rate_limit_chat_messages_per_minute=limits["messages"],
            rate_limit_chat_export_per_minute=2,
        ),
    )
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="scope-user", email=None)
    try:
        first = client.post(route, json=body)
        second = client.post(route, json=body)
    finally:
        app.dependency_overrides.clear()
        rate_limit_module.reset_limiters()
    assert first.status_code == 503
    assert second.status_code == 429


def test_sliding_window_prunes_idle_keys_before_key_cap():
    now = [0.0]
    limiter = rate_limit_module.SlidingWindowLimiter(
        limit=1, window_seconds=10.0, max_keys=1, prune_interval=5.0,
        clock=lambda: now[0],
    )
    assert limiter.allow("idle-user")
    now[0] = 11.0
    assert limiter.allow("new-user")


def test_sliding_window_fails_closed_when_key_cap_is_full():
    now = [0.0]
    limiter = rate_limit_module.SlidingWindowLimiter(
        limit=1, window_seconds=60.0, max_keys=1, prune_interval=600.0,
        clock=lambda: now[0],
    )
    assert limiter.allow("first-user")
    assert not limiter.allow("second-user")


def test_sliding_window_reclaims_expired_keys_on_capacity_pressure():
    now = [0.0]
    limiter = rate_limit_module.SlidingWindowLimiter(
        limit=1, window_seconds=10.0, max_keys=2, prune_interval=600.0,
        clock=lambda: now[0],
    )
    assert limiter.allow("old-a")
    assert limiter.allow("old-b")
    now[0] = 11.0
    # لا ننتظر دورة 600 ثانية: السعة تتعافى بمجرد انتهاء نافذة المستخدمين.
    assert limiter.allow("new-user")
    assert list(limiter._events) == ["new-user"]


def test_capacity_recovery_never_evicts_live_principal():
    now = [0.0]
    limiter = rate_limit_module.SlidingWindowLimiter(
        limit=1, window_seconds=10.0, max_keys=2, prune_interval=600.0,
        clock=lambda: now[0],
    )
    assert limiter.allow("expired-user")
    now[0] = 10.0
    assert limiter.allow("active-user")
    now[0] = 11.0
    assert not limiter.allow("new-user")
    assert list(limiter._events) == ["active-user"]


def test_sliding_window_reconfigures_limit_without_resetting_events():
    limiter = rate_limit_module.SlidingWindowLimiter(limit=3, window_seconds=60.0)
    assert limiter.allow("user-a", now=100.0)
    assert limiter.allow("user-a", now=101.0)
    limiter.set_limit(1)
    assert not limiter.allow("user-a", now=102.0)
    assert limiter.limit == 1


def test_sliding_window_limiter_is_atomic_under_concurrent_requests():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    count = 12
    limiter = rate_limit_module.SlidingWindowLimiter(limit=1, window_seconds=60.0)
    barrier = Barrier(count)

    def attempt(_):
        barrier.wait(timeout=5)
        return limiter.allow("shared-principal", now=100.0)

    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(attempt, range(count)))

    assert sum(results) == 1


def test_sliding_window_rejects_zero_key_capacity():
    with pytest.raises(ValueError, match="rate_limit_max_keys_invalid"):
        rate_limit_module.SlidingWindowLimiter(limit=1, max_keys=0)


@pytest.mark.parametrize("invalid_time", [True, float("nan"), float("inf"), "100"])
def test_sliding_window_rejects_invalid_explicit_time(invalid_time):
    limiter = rate_limit_module.SlidingWindowLimiter(limit=1, window_seconds=60.0)
    with pytest.raises(ValueError, match="rate_limit_time_invalid"):
        limiter.allow("user-a", now=invalid_time)


@pytest.mark.parametrize("invalid_clock", [True, float("nan"), float("inf")])
def test_sliding_window_rejects_invalid_clock_at_construction(invalid_clock):
    with pytest.raises(ValueError, match="rate_limit_time_invalid"):
        rate_limit_module.SlidingWindowLimiter(
            limit=1, clock=lambda: invalid_clock,
        )
