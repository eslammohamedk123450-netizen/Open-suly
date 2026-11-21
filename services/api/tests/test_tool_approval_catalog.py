from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import tool_approvals as approvals_router

client = TestClient(app)


def test_catalog_requires_authentication():
    response = client.get("/v1/tools/approvals/catalog")
    assert response.status_code == 401


def test_catalog_lists_registered_tools_and_user_approval(monkeypatch):
    class FakeStore:
        def active_scopes(self, user_id):
            assert user_id == "catalog-user"
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="catalog-user", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    items = response.json()["items"]
    by_name = {item["name"]: item for item in items}
    assert set(by_name) == {"text.analyze", "hermes.agent.turn", "ai.respond", "opencode.task.run"}
    assert by_name["text.analyze"]["approved"] is True
    assert by_name["ai.respond"]["approved"] is False
    assert by_name["ai.respond"]["available"] is False
    assert by_name["ai.respond"]["permission_scope"] == "ai.provider.run"
    assert by_name["text.analyze"]["requires_approval"] is False
    assert by_name["text.analyze"]["available"] is False
    assert by_name["hermes.agent.turn"]["available"] is False
    assert by_name["hermes.agent.turn"]["approved"] is True
    assert by_name["hermes.agent.turn"]["permission_scope"] == "agent.hermes.run"
    assert by_name["hermes.agent.turn"]["allowed_input_fields"] == ["prompt"]
    assert by_name["hermes.agent.turn"]["required_input_fields"] == ["prompt"]
    assert by_name["hermes.agent.turn"]["max_input_bytes"] == 20_100
    assert by_name["hermes.agent.turn"]["max_output_bytes"] == 52_000
    assert by_name["opencode.task.run"]["approved"] is False
    assert by_name["opencode.task.run"]["available"] is False
    assert by_name["opencode.task.run"]["permission_scope"] == "engine.opencode.run"
    assert by_name["opencode.task.run"]["supports_cancellation"] is True


def test_catalog_marks_hermes_unapproved_for_user(monkeypatch):
    class FakeStore:
        def active_scopes(self, _user_id):
            return frozenset()

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="without-grant", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    hermes = next(item for item in response.json()["items"] if item["name"] == "hermes.agent.turn")
    assert hermes["approved"] is False


def test_catalog_reports_hermes_available_only_when_runtime_is_configured(monkeypatch):
    class FakeStore:
        def active_scopes(self, _user_id):
            return frozenset()

    class FakeSettings:
        ai_provider = "disabled"
        ai_base_url = None
        ai_api_key = None
        ai_model = None
        worker_enabled = True
        hermes_agent_enabled = True
        hermes_agent_isolation_confirmed = True
        hermes_agent_base_url = "http://hermes.internal:8642"
        hermes_agent_api_key = object()
        runtime_provisioner_url = "https://runtime-provisioner.internal"
        runtime_provisioner_token = object()
        runtime_provisioner_allowed_origins = ("https://hermes-runtime.internal:8443",)

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    monkeypatch.setattr(approvals_router, "get_settings", lambda: FakeSettings())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="runtime-ready-user", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    hermes = next(item for item in response.json()["items"] if item["name"] == "hermes.agent.turn")
    assert hermes["available"] is True
    assert hermes["approved"] is False


def test_catalog_reports_ai_provider_available_only_when_fully_configured(monkeypatch):
    class FakeStore:
        def active_scopes(self, _user_id):
            return frozenset()

    class FakeSettings:
        ai_provider = "openai-compatible"
        ai_base_url = "https://provider.example/v1"
        ai_api_key = object()
        ai_model = "test-model"
        worker_enabled = True
        hermes_agent_enabled = False
        hermes_agent_isolation_confirmed = False
        hermes_agent_base_url = None
        hermes_agent_api_key = None

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    monkeypatch.setattr(approvals_router, "get_settings", lambda: FakeSettings())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="ai-ready-user", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ai_tool = next(item for item in response.json()["items"] if item["name"] == "ai.respond")
    assert ai_tool["available"] is True
    assert ai_tool["approved"] is False


def test_catalog_does_not_advertise_hermes_when_worker_or_isolation_is_off(monkeypatch):
    class FakeStore:
        def active_scopes(self, _user_id):
            return frozenset()

    class FakeSettings:
        worker_enabled = False
        ai_provider = "disabled"
        ai_base_url = None
        ai_api_key = None
        ai_model = None
        hermes_agent_enabled = True
        hermes_agent_isolation_confirmed = False
        hermes_agent_base_url = "http://hermes.internal:8642"
        hermes_agent_api_key = object()

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    monkeypatch.setattr(approvals_router, "get_settings", lambda: FakeSettings())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="worker-disabled-user", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["items"]}
    assert by_name["text.analyze"]["available"] is False
    assert by_name["ai.respond"]["available"] is False
    assert by_name["hermes.agent.turn"]["available"] is False

def test_catalog_reports_local_ollama_available_without_api_key(monkeypatch):
    class FakeStore:
        def active_scopes(self, _user_id):
            return frozenset()

    class FakeSettings:
        ai_provider = "ollama"
        ai_base_url = "http://ollama.internal:11434"
        ai_api_key = None
        ai_model = "qwen2.5:3b"
        worker_enabled = True
        hermes_agent_enabled = False
        hermes_agent_isolation_confirmed = False
        hermes_agent_base_url = None
        hermes_agent_api_key = None

    monkeypatch.setattr(approvals_router, "_store", lambda: FakeStore())
    monkeypatch.setattr(approvals_router, "get_settings", lambda: FakeSettings())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id="ollama-ready-user", email=None
    )
    try:
        response = client.get("/v1/tools/approvals/catalog")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ai_tool = next(item for item in response.json()["items"] if item["name"] == "ai.respond")
    assert ai_tool["available"] is True
    assert ai_tool["approved"] is False

