from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_conversation_list_requires_authentication():
    response = client.get("/v1/chat/conversations")
    assert response.status_code == 401


def test_conversation_create_requires_authentication():
    response = client.post("/v1/chat/conversations", json={"title": "Hello"})
    assert response.status_code == 401


def test_message_list_requires_authentication():
    response = client.get(
        "/v1/chat/conversations/00000000-0000-0000-0000-000000000001/messages"
    )
    assert response.status_code == 401


def test_add_message_requires_authentication():
    response = client.post(
        "/v1/chat/conversations/00000000-0000-0000-0000-000000000001/messages",
        json={"content": "Hello"},
    )
    assert response.status_code == 401


def test_conversation_limit_is_bounded_before_database():
    from app.core.auth import AuthenticatedUser, get_current_user
    from app.routers import chat as chat_module

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.get("/v1/chat/conversations?limit=1000")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_blank_message_is_rejected_before_database(monkeypatch):
    from app.core.auth import AuthenticatedUser, get_current_user
    from app.routers import chat as chat_module

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(
        chat_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.post(
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000001/messages",
            json={"content": "   "},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


class _OwnedConversationQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}
        self.operation = "select"
        self.values = {}

    def select(self, *_args):
        # PostgREST select() after update/delete requests representation.
        return self

    def update(self, values):
        self.operation = "update"
        self.values = values
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def execute(self):
        matches = [
            row for row in self.rows
            if all(str(row.get(key)) == str(value) for key, value in self.filters.items())
        ]
        if self.operation == "update":
            for row in matches:
                row.update(self.values)
            return type("Result", (), {"data": matches})()
        if self.operation == "delete":
            for row in matches:
                self.rows.remove(row)
            return type("Result", (), {"data": matches})()
        return type("Result", (), {"data": matches})()


class _OwnedConversationAdmin:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        assert name == "conversations"
        return _OwnedConversationQuery(self.rows)


def _as_user(user_id="owner-a"):
    from app.core.auth import AuthenticatedUser
    return AuthenticatedUser(id=user_id, email=None)


def test_rename_conversation_is_owner_scoped(monkeypatch):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    rows = [{"id": "00000000-0000-0000-0000-000000000001", "user_id": "owner-b", "title": "Private"}]
    admin = _OwnedConversationAdmin(rows)
    app.dependency_overrides[get_current_user] = lambda: _as_user("owner-a")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.patch(
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000001",
            json={"title": "Hijacked"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert rows[0]["title"] == "Private"


def test_rename_conversation_updates_owned_row(monkeypatch):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    rows = [{"id": "00000000-0000-0000-0000-000000000001", "user_id": "owner-a", "title": "Old"}]
    admin = _OwnedConversationAdmin(rows)
    app.dependency_overrides[get_current_user] = lambda: _as_user("owner-a")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.patch(
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000001",
            json={"title": "New title"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


def test_delete_conversation_is_owner_scoped(monkeypatch):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    rows = [{"id": "00000000-0000-0000-0000-000000000001", "user_id": "owner-b", "title": "Private"}]
    admin = _OwnedConversationAdmin(rows)
    app.dependency_overrides[get_current_user] = lambda: _as_user("owner-a")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.delete("/v1/chat/conversations/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert len(rows) == 1


def test_delete_conversation_removes_owned_row(monkeypatch):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    rows = [{"id": "00000000-0000-0000-0000-000000000001", "user_id": "owner-a", "title": "Mine"}]
    admin = _OwnedConversationAdmin(rows)
    app.dependency_overrides[get_current_user] = lambda: _as_user("owner-a")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.delete("/v1/chat/conversations/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert rows == []


class _IdempotentMessageQuery:
    def __init__(self, admin, table):
        self.admin = admin
        self.table = table
        self.operation = "select"
        self.filters = {}
        self.payload = None

    def select(self, *_args):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters[key] = str(value)
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self.table == "conversations":
            rows = [self.admin.conversation] if all(
                str(self.admin.conversation.get(key)) == value
                for key, value in self.filters.items()
            ) else []
            return type("Result", (), {"data": rows})()
        if self.operation == "insert":
            if any(row["id"] == self.payload.get("id") for row in self.admin.messages):
                raise RuntimeError("duplicate message id")
            row = {
                **self.payload,
                "id": self.payload.get("id", f"generated-{len(self.admin.messages)}"),
                "created_at": "2026-11-22T07:00:00Z",
            }
            self.admin.messages.append(row)
            return type("Result", (), {"data": [row]})()
        rows = [row for row in self.admin.messages if all(
            str(row.get(key)) == value for key, value in self.filters.items()
        )]
        return type("Result", (), {"data": rows})()


class _IdempotentMessageAdmin:
    def __init__(self, owner_id="owner-a"):
        self.conversation = {
            "id": "00000000-0000-0000-0000-000000000011",
            "user_id": owner_id,
        }
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        return _IdempotentMessageQuery(self, name)


def _post_idempotent_message(monkeypatch, admin, owner_id, key, content):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    app.dependency_overrides[get_current_user] = lambda: _as_user(owner_id)
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        return client.post(
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000011/messages",
            json={"content": content, "idempotency_key": key},
        )
    finally:
        app.dependency_overrides.clear()


def test_retrying_message_with_same_idempotency_key_returns_one_persisted_row(monkeypatch):
    admin = _IdempotentMessageAdmin()
    key = "00000000-0000-0000-0000-000000000021"

    first = _post_idempotent_message(monkeypatch, admin, "owner-a", key, "hello")
    retry = _post_idempotent_message(monkeypatch, admin, "owner-a", key, "hello")

    assert first.status_code == 201
    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"] == key
    assert len(admin.messages) == 1


def test_reusing_message_idempotency_key_for_different_content_conflicts(monkeypatch):
    admin = _IdempotentMessageAdmin()
    key = "00000000-0000-0000-0000-000000000022"

    first = _post_idempotent_message(monkeypatch, admin, "owner-a", key, "hello")
    conflict = _post_idempotent_message(monkeypatch, admin, "owner-a", key, "different")

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert len(admin.messages) == 1


def test_cannot_add_message_to_another_users_conversation(monkeypatch):
    from app.routers import chat as chat_module

    admin = _IdempotentMessageAdmin(owner_id="owner-b")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    response = _post_idempotent_message(
        monkeypatch,
        admin,
        "owner-a",
        "00000000-0000-0000-0000-000000000023",
        "private",
    )

    assert response.status_code == 404
    assert admin.messages == []


def test_message_history_loads_only_the_owned_conversation(monkeypatch):
    from app.core.auth import get_current_user
    from app.routers import chat as chat_module

    admin = _IdempotentMessageAdmin()
    admin.messages = [
        {
            "id": "user-message",
            "conversation_id": admin.conversation["id"],
            "user_id": "owner-a",
            "role": "user",
            "content": "hello",
            "metadata": {},
            "created_at": "2026-11-22T07:00:00Z",
        },
        {
            "id": "assistant-message",
            "conversation_id": admin.conversation["id"],
            "user_id": "owner-a",
            "role": "assistant",
            "content": "hello back",
            "metadata": {"in_reply_to": "user-message"},
            "created_at": "2026-11-22T07:00:01Z",
        },
    ]
    app.dependency_overrides[get_current_user] = lambda: _as_user("owner-a")
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.get(
            "/v1/chat/conversations/00000000-0000-0000-0000-000000000011/messages"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == ["user-message", "assistant-message"]
