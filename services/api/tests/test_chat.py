from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import chat as chat_module


client = TestClient(app)


class FakeChatQuery:
    def __init__(self, admin, table):
        self.admin = admin
        self.table = table
        self.operation = "select"
        self.filters = {}
        self.payload = None

    def select(self, _columns):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def contains(self, *_args):
        return self

    def execute(self):
        if self.table == "conversations":
            return type("Response", (), {"data": [{"id": self.admin.conversation_id}]})()
        if self.operation == "insert":
            row = {
                "id": "assistant-message-id",
                "conversation_id": self.admin.conversation_id,
                "user_id": self.admin.user_id,
                "role": "assistant",
                "content": self.payload["content"],
                "metadata": self.payload["metadata"],
                "created_at": "2026-11-22T07:00:00Z",
            }
            self.admin.inserted.append(row)
            return type("Response", (), {"data": [row]})()
        return type("Response", (), {"data": [self.admin.user_message]})()


class FakeChatAdmin:
    def __init__(self, conversation_id, user_id, message_id):
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.user_message = {
            "id": message_id, "conversation_id": conversation_id, "user_id": user_id,
            "role": "user", "content": "hello", "metadata": {},
            "created_at": "2026-11-22T07:00:00Z",
        }
        self.inserted = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        return FakeChatQuery(self, name)


def test_chat_response_persists_valid_provider_usage_metadata(monkeypatch):
    user_id = "test-user"
    conversation_id = "00000000-0000-0000-0000-000000000101"
    message_id = "00000000-0000-0000-0000-000000000102"
    admin = FakeChatAdmin(conversation_id, user_id, message_id)

    class FakeApprovalStore:
        def __init__(self, _admin):
            pass

        def active_scopes(self, _user_id):
            return frozenset({"ai.provider.run"})

    from app.core.config import Settings
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(chat_module, "ToolApprovalStore", FakeApprovalStore)
    monkeypatch.setattr(chat_module, "get_settings", lambda: Settings(
        ai_provider="openai-compatible", ai_model="test-model",
    ))

    async def fake_generate(_messages, *, on_usage=None):
        if on_usage is not None:
            on_usage({"input_tokens": 12, "output_tokens": 4, "total_tokens": 16})
        return "answer"

    monkeypatch.setattr(chat_module, "generate_reply", fake_generate)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, email=None)
    try:
        response = client.post(
            "/v1/chat/respond",
            json={"conversation_id": conversation_id, "message_id": message_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["metadata"]["usage"] == {
        "input_tokens": 12, "output_tokens": 4, "total_tokens": 16,
    }
    assert admin.inserted[0]["metadata"]["provider"] == "openai-compatible"
    assert admin.inserted[0]["metadata"]["model"] == "test-model"


def test_chat_response_requires_authenticated_user() -> None:
    response = client.post(
        "/v1/chat/respond",
        json={"conversation_id": "00000000-0000-0000-0000-000000000001", "message_id": "00000000-0000-0000-0000-000000000002"},
    )
    assert response.status_code == 401


def test_chat_response_requires_server_side_supabase_secret(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: None)
    try:
        response = client.post(
            "/v1/chat/respond",
            json={"conversation_id": "00000000-0000-0000-0000-000000000001", "message_id": "00000000-0000-0000-0000-000000000002"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Server-side Supabase secret is not configured."


def test_chat_provider_requires_persisted_user_approval_before_database_or_model(monkeypatch):
    class FakeAdmin:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False

    class FakeApprovalStore:
        def __init__(self, _admin):
            pass
        def active_scopes(self, user_id):
            assert user_id == "test-user"
            return frozenset()

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: FakeAdmin())
    monkeypatch.setattr(chat_module, "ToolApprovalStore", FakeApprovalStore)
    monkeypatch.setattr(
        chat_module,
        "generate_reply",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Provider must not be called")),
    )
    try:
        response = client.post(
            "/v1/chat/respond",
            json={
                "conversation_id": "00000000-0000-0000-0000-000000000001",
                "message_id": "00000000-0000-0000-0000-000000000002",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert "موافقة صريحة" in response.json()["detail"]



def test_stream_chat_response_persists_completed_reply_and_usage(monkeypatch):
    user_id = "stream-user"
    conversation_id = "00000000-0000-0000-0000-000000000201"
    message_id = "00000000-0000-0000-0000-000000000202"
    admin = FakeChatAdmin(conversation_id, user_id, message_id)

    class FakeApprovalStore:
        def __init__(self, _admin):
            pass

        def active_scopes(self, _user_id):
            return frozenset({"ai.provider.run"})

    from app.core.config import Settings
    monkeypatch.setattr(chat_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(chat_module, "ToolApprovalStore", FakeApprovalStore)
    monkeypatch.setattr(chat_module, "get_settings", lambda: Settings(
        ai_provider="openai-compatible", ai_model="test-model",
    ))

    async def fake_stream(_messages, *, on_usage=None):
        if on_usage is not None:
            on_usage({"input_tokens": 9, "output_tokens": 3, "total_tokens": 12})
        yield "stream "
        yield "answer"

    monkeypatch.setattr(chat_module, "stream_reply", fake_stream)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, email=None)
    try:
        response = client.post(
            "/v1/chat/respond/stream",
            json={"conversation_id": conversation_id, "message_id": message_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "stream answer" in response.text
    assert "event: complete" in response.text
    assert len(admin.inserted) == 1
    assert admin.inserted[0]["content"] == "stream answer"
    assert admin.inserted[0]["metadata"]["usage"] == {
        "input_tokens": 9, "output_tokens": 3, "total_tokens": 12,
    }
