"""اختبارات تصدير المحادثات: ملكية الحساب، RLS client، الحدود والتنقية."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.rate_limit import reset_limiters
from app.main import app
from app.routers import chat as chat_module

client = TestClient(app)
OWNER = "00000000-0000-0000-0000-000000000101"
OTHER = "00000000-0000-0000-0000-000000000202"
C1 = "10000000-0000-0000-0000-000000000001"
C2 = "10000000-0000-0000-0000-000000000002"
C3 = "10000000-0000-0000-0000-000000000003"


class ExportQuery:
    """Fake PostgREST query يحاكي filters والصفحات دون شبكة."""
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self.columns = []
        self.filters = []
        self.in_filters = {}
        self.orders = []
        self.bounds = None

    def select(self, columns):
        self.columns = columns.split(",")
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.in_filters[key] = list(values)
        return self

    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self

    def range(self, start, end):
        self.bounds = (start, end)
        return self

    def execute(self):
        self.store.queries.append(self)
        if self.store.error:
            raise RuntimeError(self.store.error)
        rows = [deepcopy(row) for row in self.store.tables.get(self.table, [])]
        for key, value in self.filters:
            rows = [row for row in rows if row.get(key) == value]
        for key, values in self.in_filters.items():
            rows = [row for row in rows if row.get(key) in values]
        for key, desc in reversed(self.orders):
            rows.sort(key=lambda row: row.get(key) or "", reverse=desc)
        if self.bounds is not None:
            start, end = self.bounds
            rows = rows[start:end + 1]
        return SimpleNamespace(data=[
            {field: row.get(field) for field in self.columns}
            for row in rows
        ])


class ExportStore:
    def __init__(self, conversations=None, messages=None, error=None):
        self.tables = {"conversations": conversations or [], "messages": messages or []}
        self.error = error
        self.queries = []

    def table(self, name):
        assert name in self.tables
        return ExportQuery(self, name)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.fixture(autouse=True)
def clean_export_dependencies():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(chat_module.get_chat_export_client, None)
    reset_limiters()
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(chat_module.get_chat_export_client, None)
    reset_limiters()


def auth_owner():
    return AuthenticatedUser(id=OWNER, email=None)


def setup_export(store):
    app.dependency_overrides[get_current_user] = auth_owner
    app.dependency_overrides[chat_module.get_chat_export_client] = lambda: store


def conversation(cid, owner, title, created):
    return {
        "id": cid, "user_id": owner, "title": title,
        "created_at": created, "updated_at": created,
        "internal": "must not be exported",
    }


def message(mid, cid, owner, role, content, created):
    return {
        "id": mid, "conversation_id": cid, "user_id": owner, "role": role,
        "content": content, "created_at": created,
        "metadata": {"provider": "private-provider", "secret": "never export"},
    }


def test_chat_export_requires_authenticated_bearer():
    response = client.get("/v1/chat/export")
    assert response.status_code == 401


def test_export_client_uses_user_jwt_and_never_service_role(monkeypatch):
    marker = object()
    seen = []
    monkeypatch.setattr(chat_module, "get_supabase_client", lambda token: (seen.append(token), marker)[1])
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: (_ for _ in ()).throw(AssertionError("admin client must not be used")))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-user-jwt")
    assert chat_module.get_chat_export_client(credentials) is marker
    assert seen == ["test-user-jwt"]


def test_export_client_rejects_missing_bearer_and_missing_configuration(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        chat_module.get_chat_export_client(None)
    assert missing.value.status_code == 401
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-user-jwt")
    monkeypatch.setattr(chat_module, "get_supabase_client", lambda _token: None)
    with pytest.raises(HTTPException) as unavailable:
        chat_module.get_chat_export_client(credentials)
    assert unavailable.value.status_code == 503


def test_export_is_owner_scoped_and_drops_metadata_and_unselected_fields():
    store = ExportStore(
        conversations=[
            conversation(C1, OWNER, "محادثة خاصة", "2026-11-23T08:00:00Z"),
            conversation(C2, OTHER, "foreign", "2026-11-23T09:00:00Z"),
        ],
        messages=[
            message("m1", C1, OWNER, "user", "hello", "2026-11-23T08:01:00Z"),
            message("m2", C1, OWNER, "assistant", "answer", "2026-11-23T08:02:00Z"),
            message("m3", C1, OTHER, "assistant", "foreign owner message", "2026-11-23T08:03:00Z"),
            message("m4", C2, OWNER, "user", "foreign conversation", "2026-11-23T08:04:00Z"),
        ],
    )
    setup_export(store)
    response = client.get("/v1/chat/export")
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_count"] == 1
    assert payload["message_count"] == 2
    assert payload["conversations"][0]["id"] == C1
    assert [row["id"] for row in payload["messages"]] == ["m1", "m2"]
    assert all("metadata" not in row and "user_id" not in row for row in payload["messages"])
    assert "secret" not in response.text and "private-provider" not in response.text
    assert "internal" not in response.text
    assert all(("user_id", OWNER) in query.filters for query in store.queries)
    assert store.queries[0].columns == ["id", "title", "created_at", "updated_at"]
    assert store.queries[1].columns == ["id", "conversation_id", "role", "content", "created_at"]


def test_export_paginates_message_rows(monkeypatch):
    monkeypatch.setattr(chat_module, "CHAT_EXPORT_MESSAGE_PAGE_SIZE", 2)
    store = ExportStore(
        conversations=[conversation(C1, OWNER, "test", "2026-11-23T08:00:00Z")],
        messages=[
            message("m1", C1, OWNER, "user", "one", "2026-11-23T08:01:00Z"),
            message("m2", C1, OWNER, "assistant", "two", "2026-11-23T08:02:00Z"),
            message("m3", C1, OWNER, "user", "three", "2026-11-23T08:03:00Z"),
        ],
    )
    setup_export(store)
    response = client.get("/v1/chat/export")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["messages"]] == ["m1", "m2", "m3"]
    message_queries = [query for query in store.queries if query.table == "messages"]
    assert [query.bounds for query in message_queries] == [(0, 1), (2, 3)]


def test_export_reports_conversation_cap_without_querying_messages(monkeypatch):
    monkeypatch.setattr(chat_module, "CHAT_EXPORT_MAX_CONVERSATIONS", 1)
    monkeypatch.setattr(chat_module, "CHAT_EXPORT_CONVERSATION_PAGE_SIZE", 1)
    store = ExportStore(
        conversations=[
            conversation(C1, OWNER, "first", "2026-11-23T08:00:00Z"),
            conversation(C3, OWNER, "second", "2026-11-23T09:00:00Z"),
        ],
    )
    setup_export(store)
    response = client.get("/v1/chat/export")
    payload = response.json()
    assert response.status_code == 200
    assert payload["truncated"] is True
    assert payload["truncation_reason"] == "conversation_limit"
    assert payload["conversation_count"] == 1
    assert payload["message_count"] == 0
    assert not any(query.table == "messages" for query in store.queries)


def test_export_rate_limit_applies_before_database_reads(monkeypatch):
    from app.core.config import Settings
    import app.core.rate_limit as limiter_module

    monkeypatch.setattr(
        limiter_module, "get_settings",
        lambda: Settings(rate_limit_chat_export_per_minute=1),
    )
    store = ExportStore(conversations=[conversation(C1, OWNER, "test", "2026-11-23T08:00:00Z")])
    setup_export(store)
    assert client.get("/v1/chat/export").status_code == 200
    query_count = len(store.queries)
    response = client.get("/v1/chat/export")
    assert response.status_code == 429
    assert len(store.queries) == query_count


def test_export_sanitizes_database_failures(monkeypatch):
    store = ExportStore(error="private fake DB diagnostic")
    setup_export(store)
    response = client.get("/v1/chat/export")
    assert response.status_code == 503
    assert response.json()["detail"] == "تعذر تجهيز تصدير المحادثات الآن."
    assert "private fake DB diagnostic" not in response.text
