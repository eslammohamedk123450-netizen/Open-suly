from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
import app.routers.usage as usage


client = TestClient(app)
USER_ID = "00000000-0000-0000-0000-000000000111"
OTHER_ID = "00000000-0000-0000-0000-000000000222"


class UsageQuery:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.columns = []
        self.filters = []
        self.orders = []
        self.limit_value = None

    def select(self, columns):
        self.columns = columns.split(",")
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.db.queries.append(self)
        if self.db.failure:
            raise RuntimeError("private fake database diagnostic")
        rows = [
            deepcopy(row) for row in self.db.rows
            if all(row.get(key) == value for key, value in self.filters)
        ]
        for key, desc in reversed(self.orders):
            rows.sort(key=lambda row: row.get(key) or "", reverse=desc)
        if self.limit_value is not None:
            rows = rows[:self.limit_value]
        return SimpleNamespace(data=[{field: row.get(field) for field in self.columns} for row in rows])


class FakeUsageClient:
    def __init__(self, rows=None, failure=False):
        self.rows = rows or []
        self.failure = failure
        self.queries = []

    def table(self, name):
        assert name == "messages"
        return UsageQuery(self, name)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _message(user_id, role, input_tokens, output_tokens, timestamp, *, extra=None):
    metadata = {"provider": "fake-provider", "model": "private-model", "secret_note": "never expose"}
    if input_tokens is not None and output_tokens is not None:
        metadata["usage"] = {
            "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": -999,
        }
    if extra is not None:
        metadata["usage"] = extra
    return {
        "user_id": user_id, "role": role, "metadata": metadata,
        "created_at": timestamp, "content": "private chat text",
    }


def configure(monkeypatch, fake, *, user_id=USER_ID):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, email=None)
    app.dependency_overrides[usage.get_chat_usage_client] = lambda: fake
    rate_calls = []
    monkeypatch.setattr(
        usage, "apply_rate_limit",
        lambda *args, **kwargs: rate_calls.append((args, kwargs)),
    )
    return TestClient(app), rate_calls


def cleanup():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(usage.get_chat_usage_client, None)


def test_chat_usage_requires_authentication():
    try:
        response = TestClient(app).get("/v1/usage/chat")
        assert response.status_code == 401
    finally:
        cleanup()


def test_usage_client_uses_user_token(monkeypatch):
    marker = object()
    tokens = []
    monkeypatch.setattr(usage, "get_supabase_client", lambda token: (tokens.append(token), marker)[1])
    result = usage.get_chat_usage_client(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="user-token-not-admin")
    )
    assert result is marker
    assert tokens == ["user-token-not-admin"]


def test_chat_usage_is_owner_and_assistant_scoped_and_never_returns_metadata(monkeypatch):
    fake = FakeUsageClient([
        _message(USER_ID, "assistant", 11, 4, "2026-11-23T10:00:00Z"),
        _message(USER_ID, "user", 500, 500, "2026-11-23T09:59:00Z"),
        _message(OTHER_ID, "assistant", 900, 100, "2026-11-23T09:58:00Z"),
        _message(USER_ID, "assistant", 12, 5, "2026-11-23T09:57:00Z", extra={"input_tokens": "12", "output_tokens": 5}),
        _message(USER_ID, "assistant", None, None, "2026-11-23T09:56:00Z"),
        _message(USER_ID, "assistant", 3, 2, "2026-11-23T09:55:00Z"),
    ])
    api, rate_calls = configure(monkeypatch, fake)
    try:
        response = api.get("/v1/usage/chat")
        assert response.status_code == 200
        assert response.json() == {
            "scope": "chat",
            "coverage": "all_assistant_messages",
            "assistant_messages_checked": 4,
            "usage_records": 2,
            "input_tokens": 14,
            "output_tokens": 6,
            "total_tokens": 20,
            "truncated": False,
            "sample_limit": 500,
            "period_start": "2026-11-23T09:55:00Z",
            "period_end": "2026-11-23T10:00:00Z",
        }
        assert len(fake.queries) == 1
        query = fake.queries[0]
        assert query.columns == ["metadata", "created_at"]
        assert ("user_id", USER_ID) in query.filters
        assert ("role", "assistant") in query.filters
        assert query.limit_value == 501
        assert rate_calls == [((f"chat_usage:{USER_ID}",), {"capacity": 20, "refill_seconds": 60.0})]
        assert "secret_note" not in response.text
        assert "private chat text" not in response.text
        assert "private-model" not in response.text
    finally:
        cleanup()


def test_chat_usage_is_bounded_to_latest_500(monkeypatch):
    rows = [
        _message(USER_ID, "assistant", 1, 2, f"2026-11-23T10:{index:02d}:00Z")
        for index in range(501)
    ]
    fake = FakeUsageClient(rows)
    api, _rate_calls = configure(monkeypatch, fake)
    try:
        response = api.get("/v1/usage/chat")
        payload = response.json()
        assert response.status_code == 200
        assert payload["assistant_messages_checked"] == 500
        assert payload["usage_records"] == 500
        assert payload["input_tokens"] == 500
        assert payload["output_tokens"] == 1000
        assert payload["total_tokens"] == 1500
        assert payload["truncated"] is True
        assert payload["coverage"] == "latest_500_assistant_messages"
        assert fake.queries[0].limit_value == 501
    finally:
        cleanup()


def test_chat_usage_sanitizes_database_errors(monkeypatch):
    fake = FakeUsageClient(failure=True)
    api, _rate_calls = configure(monkeypatch, fake)
    try:
        response = api.get("/v1/usage/chat")
        assert response.status_code == 503
        assert response.json()["detail"] == "Chat usage is temporarily unavailable."
        assert "private fake database diagnostic" not in response.text
    finally:
        cleanup()
