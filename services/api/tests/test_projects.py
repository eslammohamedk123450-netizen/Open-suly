from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import projects as projects_module

client = TestClient(app)


def test_projects_require_authentication():
    assert client.get("/v1/projects").status_code == 401
    assert client.post("/v1/projects", json={"name": "My work"}).status_code == 401


def test_project_creation_requires_server_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(projects_module, "get_supabase_admin_client", lambda: None)
    try:
        response = client.post("/v1/projects", json={"name": "My work"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503


def test_project_name_cannot_be_blank_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(
        projects_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.post("/v1/projects", json={"name": "   "})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_project_update_requires_at_least_one_field():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    try:
        response = client.patch(
            "/v1/projects/00000000-0000-0000-0000-000000000001",
            json={},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_project_delete_requires_authentication():
    response = client.delete("/v1/projects/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 401
