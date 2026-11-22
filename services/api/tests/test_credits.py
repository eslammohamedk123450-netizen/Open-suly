from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
import app.routers.credits as credits


USER_ID = "00000000-0000-0000-0000-000000000111"
OTHER_ID = "00000000-0000-0000-0000-000000000222"


class CreditQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.filters = []
        self.order_by = None
        self.limit_value = None
        self.columns = None

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, key, desc=False, **_kwargs):
        self.order_by = (key, desc)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.client.queries.append(self)
        if self.client.failure:
            raise RuntimeError("fake database diagnostic should never reach the client")
        rows = [
            deepcopy(row) for row in self.client.tables.get(self.table_name, [])
            if all(row.get(key) == value for key, value in self.filters)
        ]
        if self.order_by:
            key, desc = self.order_by
            rows.sort(key=lambda row: row.get(key) or "", reverse=desc)
        if self.limit_value is not None:
            rows = rows[:self.limit_value]
        return SimpleNamespace(data=rows)


class FakeCreditClient:
    def __init__(self, tables=None, failure=False):
        self.tables = tables or {}
        self.failure = failure
        self.queries = []

    def table(self, name):
        return CreditQuery(self, name)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def configure(monkeypatch, client, *, enabled=True, user_id=USER_ID):
    monkeypatch.setattr(
        credits, "get_settings",
        lambda: SimpleNamespace(engine_credits_enabled=enabled),
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, email=None)
    app.dependency_overrides[credits.get_credit_client] = lambda: client
    return TestClient(app)


def cleanup():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(credits.get_credit_client, None)


def test_credit_summary_requires_authentication():
    try:
        assert TestClient(app).get("/v1/credits").status_code == 401
    finally:
        cleanup()


def test_credit_summary_feature_flag_blocks_client_creation(monkeypatch):
    monkeypatch.setattr(
        credits, "get_settings",
        lambda: SimpleNamespace(engine_credits_enabled=False),
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID, email=None)
    monkeypatch.setattr(
        credits, "get_supabase_client",
        lambda _token: (_ for _ in ()).throw(AssertionError("database client must not be created")),
    )
    try:
        response = TestClient(app).get("/v1/credits")
        assert response.status_code == 503
        assert response.json()["detail"] == "Credit ledger is disabled on this server."
    finally:
        cleanup()


def test_credit_client_uses_user_token_not_service_role(monkeypatch):
    marker = object()
    seen = []
    monkeypatch.setattr(
        credits, "get_settings",
        lambda: SimpleNamespace(engine_credits_enabled=True),
    )
    monkeypatch.setattr(
        credits, "get_supabase_client",
        lambda token: (seen.append(token), marker)[1],
    )
    from fastapi.security import HTTPAuthorizationCredentials
    result = credits.get_credit_client(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="verified-user-token")
    )
    assert result is marker
    assert seen == ["verified-user-token"]


def test_credit_summary_returns_bounded_owner_only_projection(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    reservations = [
        {
            "id": f"reservation-{index}",
            "user_id": USER_ID,
            "engine_id": "opencode",
            "reserved_credits": index + 1,
            "settled_credits": None,
            "status": "reserved",
            "expires_at": now,
            "created_at": f"2026-11-22T09:{index:02d}:00+00:00",
            "completed_at": None,
            "metadata": {"internal_note": "must not be returned"},
        }
        for index in range(30)
    ]
    transactions = [
        {
            "id": f"transaction-{index}",
            "user_id": USER_ID,
            "reservation_id": f"reservation-{index}",
            "transaction_type": "reserve",
            "available_delta": -10,
            "reserved_delta": 10,
            "engine_id": "opencode",
            "created_at": f"2026-11-22T09:{index:02d}:00+00:00",
            "metadata": {"private": "must not be returned"},
        }
        for index in range(55)
    ]
    client = FakeCreditClient({
        "credit_accounts": [
            {"user_id": USER_ID, "available_credits": 125, "reserved_credits": 20, "updated_at": now},
            {"user_id": OTHER_ID, "available_credits": 999, "reserved_credits": 0, "updated_at": now},
        ],
        "credit_reservations": reservations + [
            {"id": "other-reservation", "user_id": OTHER_ID, "engine_id": "hermes-agent",
             "reserved_credits": 99, "settled_credits": None, "status": "reserved",
             "expires_at": now, "created_at": now, "completed_at": None},
        ],
        "credit_ledger": transactions + [
            {"id": "other-transaction", "user_id": OTHER_ID, "reservation_id": None,
             "transaction_type": "grant", "available_delta": 999, "reserved_delta": 0,
             "engine_id": None, "created_at": now},
        ],
    })
    api = configure(monkeypatch, client)
    try:
        response = api.get("/v1/credits")
        assert response.status_code == 200
        payload = response.json()
        assert payload["account"] == {
            "available_credits": 125, "reserved_credits": 20, "updated_at": now,
        }
        assert len(payload["reservations"]) == 25
        assert payload["reservations"][0]["id"] == "reservation-29"
        assert len(payload["transactions"]) == 50
        assert payload["transactions"][0]["id"] == "transaction-54"
        assert all("metadata" not in item for item in payload["transactions"])
        assert all("user_id" not in item for item in payload["reservations"])
        assert [query.table_name for query in client.queries] == [
            "credit_accounts", "credit_reservations", "credit_ledger",
        ]
        assert all(("user_id", USER_ID) in query.filters for query in client.queries)
        assert [query.limit_value for query in client.queries] == [1, 25, 50]
    finally:
        cleanup()


def test_credit_summary_returns_zero_account_before_first_grant(monkeypatch):
    client = FakeCreditClient({
        "credit_accounts": [], "credit_reservations": [], "credit_ledger": [],
    })
    api = configure(monkeypatch, client)
    try:
        response = api.get("/v1/credits")
        assert response.status_code == 200
        assert response.json() == {
            "account": {"available_credits": 0, "reserved_credits": 0, "updated_at": None},
            "reservations": [], "transactions": [],
        }
    finally:
        cleanup()


def test_credit_summary_sanitizes_database_failure(monkeypatch):
    client = FakeCreditClient(failure=True)
    api = configure(monkeypatch, client)
    try:
        response = api.get("/v1/credits")
        assert response.status_code == 503
        assert response.json()["detail"] == (
            "Credit ledger is unavailable. Verify its migration and server flag."
        )
        assert "fake database diagnostic" not in response.text
    finally:
        cleanup()


def test_credit_summary_rejects_malformed_balance(monkeypatch):
    client = FakeCreditClient({
        "credit_accounts": [
            {"user_id": USER_ID, "available_credits": "not-an-int", "reserved_credits": 1}
        ],
        "credit_reservations": [], "credit_ledger": [],
    })
    api = configure(monkeypatch, client)
    try:
        response = api.get("/v1/credits")
        assert response.status_code == 503
        assert "not-an-int" not in response.text
    finally:
        cleanup()
