from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import tool_approvals as approvals_module


client = TestClient(app)


class FakeAdmin:
    def __init__(self, rpc_value=None):
        self.rpc_value = rpc_value
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data=self.rpc_value)
        )

    def table(self, name):
        self.calls.append(("table", name))
        query = FakeQuery()
        return query


class FakeQuery:
    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


def test_approval_endpoints_require_authentication():
    assert client.get("/v1/tools/approvals").status_code == 401
    assert client.get("/v1/tools/approvals/events").status_code == 401
    assert client.post(
        "/v1/tools/approvals", json={"permission_scope": "files.read"}
    ).status_code == 401


def test_user_cannot_grant_scope_not_registered_for_approval(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="user-1", email=None
    )
    monkeypatch.setattr(
        approvals_module.TOOL_REGISTRY,
        "requires_approval_scope",
        lambda _scope: False,
    )
    monkeypatch.setattr(
        approvals_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be called")),
    )
    try:
        response = client.post(
            "/v1/tools/approvals", json={"permission_scope": "admin.root"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_grant_uses_verified_user_identity_and_never_client_user_id(monkeypatch):
    admin = FakeAdmin("approval-123")
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="verified-user", email=None
    )
    monkeypatch.setattr(
        approvals_module.TOOL_REGISTRY,
        "requires_approval_scope",
        lambda scope: scope == "files.read",
    )
    monkeypatch.setattr(
        approvals_module, "get_supabase_admin_client", lambda: admin
    )
    try:
        response = client.post(
            "/v1/tools/approvals",
            json={"permission_scope": "files.read", "user_id": "attacker-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == "approval-123"
    assert admin.calls == [(
        "grant_tool_approval",
        {
            "p_user_id": "verified-user",
            "p_permission_scope": "files.read",
            "p_actor_user_id": "verified-user",
        },
    )]


def test_invalid_scope_format_is_rejected_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="user-1", email=None
    )
    monkeypatch.setattr(
        approvals_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be called")),
    )
    try:
        response = client.post(
            "/v1/tools/approvals", json={"permission_scope": "files.read *"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
