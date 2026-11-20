from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import project_files as files_module

client = TestClient(app)
PROJECT_ID = "00000000-0000-0000-0000-000000000001"
REVISION_ID = "00000000-0000-0000-0000-000000000002"


def test_project_files_require_authentication():
    assert client.get(f"/v1/projects/{PROJECT_ID}/files").status_code == 401
    assert client.put(f"/v1/projects/{PROJECT_ID}/file?path=main.py", json={"content": "print(1)"}).status_code == 401


def test_project_file_history_requires_authentication():
    assert client.get(f"/v1/projects/{PROJECT_ID}/file/history?path=main.py").status_code == 401
    assert client.get(f"/v1/projects/{PROJECT_ID}/file/history/{REVISION_ID}").status_code == 401
    assert client.post(f"/v1/projects/{PROJECT_ID}/file/history/{REVISION_ID}/restore").status_code == 401


def test_project_file_path_rejects_traversal_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(
        files_module, "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.get(f"/v1/projects/{PROJECT_ID}/file?path=../secrets.txt")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_project_file_path_rejects_environment_secrets():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    try:
        response = client.get(f"/v1/projects/{PROJECT_ID}/file?path=.env.production")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_project_file_save_rejects_nul_content_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(
        files_module, "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.put(
            f"/v1/projects/{PROJECT_ID}/file?path=src/main.py",
            json={"content": "print('safe')\\u0000"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_project_file_save_rejects_oversized_utf8_content():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    try:
        response = client.put(
            f"/v1/projects/{PROJECT_ID}/file?path=src/main.py",
            json={"content": "é" * 140000},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 413
