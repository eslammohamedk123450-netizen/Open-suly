from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import chat as chat_module


client = TestClient(app)


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
