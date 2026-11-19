from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.core import auth as auth_module
from app.main import app


class FakeClient:
    def __init__(self, user=None):
        self.auth = SimpleNamespace(
            get_user=Mock(return_value=SimpleNamespace(user=user))
        )
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True


client = TestClient(app)


def test_auth_me_requires_bearer_token() -> None:
    response = client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_me_returns_only_supabase_validated_identity(monkeypatch) -> None:
    user = SimpleNamespace(id="user-123", email="person@example.com")
    fake = FakeClient(user=user)
    monkeypatch.setattr(auth_module, "get_supabase_client", lambda: fake)

    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer verified-test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-123",
        "email": "person@example.com",
    }
    fake.auth.get_user.assert_called_once_with("verified-test-token")
    assert fake.closed is True


def test_auth_me_returns_service_unavailable_without_supabase(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "get_supabase_client", lambda: None)

    response = client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer any-token"},
    )

    assert response.status_code == 503
