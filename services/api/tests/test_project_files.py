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
            json={"content": "print('safe')\u0000"},
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


def test_project_file_history_path_rejects_traversal_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(
        files_module, "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.get(f"/v1/projects/{PROJECT_ID}/file/history?path=../secrets.txt")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422




class _FakeQuery:
    def __init__(self, table_name, project_id):
        self.table_name = table_name
        self.project_id = project_id
        self.action = "select"
        self.filters = {}

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_args):
        return self

    def update(self, _values):
        self.action = "update"
        return self

    def insert(self, _values):
        self.action = "insert"
        return self

    def execute(self):
        if self.table_name == "projects":
            return type("Result", (), {"data": [{"id": self.project_id}]})()
        if self.table_name == "project_files" and self.action == "select":
            return type("Result", (), {"data": [{
                "id": "00000000-0000-0000-0000-000000000003",
                "updated_at": "2026-11-20T10:00:00+00:00",
            }]})()
        if self.table_name == "project_files" and self.action == "update":
            # Simulate compare-and-swap: no row matches the stale timestamp.
            return type("Result", (), {"data": []})()
        raise AssertionError(f"Unexpected query: {self.table_name}/{self.action}")


class _FakeAdminClient:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        return _FakeQuery(name, PROJECT_ID)


def test_project_file_stale_save_returns_conflict(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(files_module, "get_supabase_admin_client", _FakeAdminClient)
    try:
        response = client.put(
            f"/v1/projects/{PROJECT_ID}/file?path=src/main.py",
            json={
                "content": "print('new')",
                "expected_updated_at": "2026-11-20T09:00:00+00:00",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert "changed elsewhere" in response.json()["detail"]


def test_project_file_restore_requires_expected_version():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    try:
        response = client.post(
            f"/v1/projects/{PROJECT_ID}/file/history/{REVISION_ID}/restore",
            json={},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
