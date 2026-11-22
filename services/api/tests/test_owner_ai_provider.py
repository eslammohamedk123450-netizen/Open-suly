from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import Settings
from app.main import app
from app.routers import owner_ai_provider as owner_module


client = TestClient(app)


class FakeRpc:
    def __init__(self, admin, name, params):
        self.admin = admin
        self.name = name
        self.params = params

    def execute(self):
        self.admin.calls.append((self.name, self.params))
        if self.name == "suly_ai_provider_config_get":
            return type("Response", (), {"data": self.admin.config})()
        if self.name == "suly_ai_provider_config_set":
            self.admin.config = self.params["p_config"]
            return type("Response", (), {"data": None})()
        raise AssertionError("Unexpected RPC name")


class FakeAdmin:
    def __init__(self, config=None):
        self.config = config
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def rpc(self, name, params):
        return FakeRpc(self, name, params)


def _set_user(email="owner@example.test", verified=True):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="owner-user-id", email=email, email_verified=verified
    )


def _clear_user():
    app.dependency_overrides.clear()


def test_non_owner_cannot_read_or_write_provider_settings(monkeypatch):
    admin = FakeAdmin()
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email="owner@example.test"))
    monkeypatch.setattr(owner_module, "get_supabase_admin_client", lambda: admin)
    _set_user("other@example.test", verified=True)
    try:
        read = client.get("/v1/owner/ai-provider")
        write = client.put("/v1/owner/ai-provider", json={
            "base_url": "https://provider.example/v1",
            "model": "test-model",
            "api_key": "test-only-not-a-real-key",
        })
    finally:
        _clear_user()

    assert read.status_code == 403
    assert write.status_code == 403
    assert admin.calls == []


def test_owner_must_have_verified_email(monkeypatch):
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email="owner@example.test"))
    _set_user("owner@example.test", verified=False)
    try:
        response = client.get("/v1/owner/ai-provider")
    finally:
        _clear_user()
    assert response.status_code == 403


def test_missing_owner_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email=None))
    _set_user("owner@example.test", verified=True)
    try:
        response = client.get("/v1/owner/ai-provider")
    finally:
        _clear_user()
    assert response.status_code == 503


def test_status_never_returns_vault_api_key(monkeypatch):
    private_test_key = "test-only-not-a-real-key"
    admin = FakeAdmin({
        "provider": "openai-compatible",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
        "api_key": private_test_key,
    })
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email="owner@example.test"))
    monkeypatch.setattr(owner_module, "get_supabase_admin_client", lambda: admin)
    _set_user()
    try:
        response = client.get("/v1/owner/ai-provider")
    finally:
        _clear_user()

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["api_key_set"] is True
    assert "api_key" not in response.json()
    assert private_test_key not in response.text


def test_owner_can_store_key_in_vault_without_receiving_it_back(monkeypatch):
    private_test_key = "test-only-not-a-real-key"
    admin = FakeAdmin()
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email="owner@example.test"))
    monkeypatch.setattr(owner_module, "get_supabase_admin_client", lambda: admin)
    _set_user()
    try:
        response = client.put("/v1/owner/ai-provider", json={
            "provider": "openai-compatible",
            "base_url": "https://provider.example/v1",
            "model": "test-model",
            "api_key": private_test_key,
        })
    finally:
        _clear_user()

    assert response.status_code == 200
    assert response.json()["source"] == "vault"
    assert "api_key" not in response.json()
    assert private_test_key not in response.text
    assert admin.config["api_key"] == private_test_key
    assert admin.calls[0][0] == "suly_ai_provider_config_set"


def test_invalid_insecure_provider_url_does_not_echo_key(monkeypatch):
    private_test_key = "test-only-not-a-real-key"
    monkeypatch.setattr(owner_module, "get_settings", lambda: Settings(suly_owner_email="owner@example.test"))
    _set_user()
    try:
        response = client.put("/v1/owner/ai-provider", json={
            "base_url": "http://localhost:8000",
            "model": "test-model",
            "api_key": private_test_key,
        })
    finally:
        _clear_user()

    assert response.status_code == 422
    assert private_test_key not in response.text
