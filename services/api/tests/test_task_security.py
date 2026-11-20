from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import tasks as tasks_module


client = TestClient(app)
TASK_ID = "00000000-0000-0000-0000-000000000001"


class Query:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.selection = None
        self.filters = []
        self.update_payload = None

    def select(self, columns):
        self.selection = columns
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def in_(self, key, values):
        self.filters.append(("in", key, values))
        return self

    def execute(self):
        rows = self.rows
        if self.selection and self.selection != "*":
            allowed = set(self.selection.split(","))
            rows = [{key: value for key, value in row.items() if key in allowed} for row in rows]
        return SimpleNamespace(data=rows)


class Admin:
    def __init__(self, step_rows=None):
        self.step_query = Query(step_rows)
        self.task_query = Query([])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def table(self, name):
        return self.step_query if name == "task_steps" else self.task_query


def auth_user():
    return AuthenticatedUser(id="owner-1", email=None)


def test_task_detail_never_returns_worker_lease_credentials(monkeypatch):
    admin = Admin([{
        "id": "step-1",
        "task_id": TASK_ID,
        "user_id": "owner-1",
        "step_key": "first",
        "status": "running",
        "lease_owner": "worker-secret",
        "lease_token": "opaque-secret",
        "lease_expires_at": "2026-11-20T12:00:00Z",
    }])
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(
        tasks_module, "_owned_task",
        lambda *_args: {"id": TASK_ID, "user_id": "owner-1", "status": "running"},
    )
    app.dependency_overrides[get_current_user] = auth_user
    try:
        response = client.get(f"/v1/tasks/{TASK_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "lease_token" not in admin.step_query.selection
    assert "lease_owner" not in admin.step_query.selection
    assert "lease_expires_at" not in admin.step_query.selection
    body = response.json()
    assert "lease_token" not in body["steps"][0]
    assert "lease_owner" not in body["steps"][0]


def test_cancel_update_is_conditioned_on_nonterminal_state(monkeypatch):
    admin = Admin()
    states = iter([
        {"id": TASK_ID, "user_id": "owner-1", "status": "running"},
        {"id": TASK_ID, "user_id": "owner-1", "status": "completed"},
    ])
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "_owned_task", lambda *_args: next(states))
    app.dependency_overrides[get_current_user] = auth_user
    try:
        response = client.post(f"/v1/tasks/{TASK_ID}/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert ("in", "status", ["queued", "planning", "ready", "running", "waiting_approval"]) in admin.task_query.filters
