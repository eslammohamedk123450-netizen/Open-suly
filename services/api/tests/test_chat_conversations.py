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
