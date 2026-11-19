from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.routers import tasks as tasks_module


client = TestClient(app)


def test_tasks_require_authentication() -> None:
    response = client.get("/v1/tasks")
    assert response.status_code == 401


def test_task_creation_requires_server_side_database_secret(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: None)
    try:
        response = client.post(
            "/v1/tasks",
            json={"request": "Prepare a research plan", "idempotency_key": "test-key-0001"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Task service is not configured on the server."


def test_task_request_rejects_blank_content() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks",
            json={"request": "   ", "idempotency_key": "test-key-0002"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_task_planning_requires_authentication() -> None:
    response = client.post(
        "/v1/tasks/00000000-0000-0000-0000-000000000001/plan",
        json={"steps": [{"step_key": "first", "title": "First step"}]},
    )
    assert response.status_code == 401


def test_task_plan_rejects_forward_dependency_before_database(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(
        tasks_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/plan",
            json={"steps": [
                {"step_key": "first", "title": "First step", "depends_on": ["second"]},
                {"step_key": "second", "title": "Second step"},
            ]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "earlier" in response.json()["detail"]


def test_task_plan_rejects_duplicate_step_keys_before_database(monkeypatch) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(
        tasks_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/plan",
            json={"steps": [
                {"step_key": "same", "title": "First"},
                {"step_key": "same", "title": "Second"},
            ]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
