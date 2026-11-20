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


from types import SimpleNamespace


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return SimpleNamespace(data=self.rows)


class _FakeAdmin:
    def __init__(self, task):
        self.task = task
        self.rpc_calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, _name): return _FakeQuery([self.task] if self.task else [])
    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={
            "task_id": args["p_task_id"], "status": "ready", "step_count": len(args["p_steps"])
        }))


def test_auto_plan_generates_supported_text_analysis_plan(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(worker_enabled=True))
    admin = _FakeAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user",
        "status": "queued",
        "request": "analyze: SULY is an intelligent partner",
    })
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/auto-plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["planner"] == "deterministic-v1"
    assert body["status"] == "ready"
    assert body["steps"][0]["input"]["operation"] == "text.analyze"
    assert admin.rpc_calls[0][0] == "plan_task"


def test_auto_plan_fails_closed_for_unsupported_task(monkeypatch):
    admin = _FakeAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user",
        "status": "queued",
        "request": "Build a full Android application",
    })
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/auto-plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "text analysis only" in response.json()["detail"]
    assert admin.rpc_calls == []


def test_auto_plan_requires_authentication():
    response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/auto-plan")
    assert response.status_code == 401


class _RetryRpc:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def rpc(self, name, args):
        self.calls.append((name, args))
        def execute():
            if self.error:
                raise RuntimeError(self.error)
            return SimpleNamespace(data=self.result)
        return SimpleNamespace(execute=execute)


def test_retry_failed_task_calls_bounded_owner_scoped_rpc(monkeypatch):
    admin = _RetryRpc({
        "task_id": "00000000-0000-0000-0000-000000000001",
        "status": "ready",
        "reset_steps": 1,
        "manual_retry_count": 1,
        "manual_retry_limit": 2,
    })
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/retry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["manual_retry_count"] == 1
    assert admin.calls == [("retry_failed_task", {
        "p_task_id": "00000000-0000-0000-0000-000000000001",
        "p_user_id": "test-user",
    })]


def test_retry_failed_task_rejects_manual_retry_limit(monkeypatch):
    admin = _RetryRpc(error="manual_retry_limit_reached")
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/retry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "retry limit" in response.json()["detail"]

class _DetailQuery:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def limit(self, *_args): return self
    def execute(self): return SimpleNamespace(data=self.rows)


class _TaskDetailAdmin:
    def __init__(self):
        self.tables = {
            "tasks": [{
                "id": "00000000-0000-0000-0000-000000000001",
                "user_id": "test-user",
                "status": "running",
            }],
            "task_steps": [{"id": "step-1", "status": "running"}],
            "engine_runs": [{
                "id": "run-1",
                "step_id": "step-1",
                "engine_id": "hermes-agent",
                "status": "running",
                "attempt_count": 1,
            }],
        }
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name): return _DetailQuery(self.tables[name])


def test_task_detail_includes_owner_scoped_engine_run_history(monkeypatch):
    admin = _TaskDetailAdmin()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.get("/v1/tasks/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["steps"][0]["status"] == "running"
    assert body["engine_runs"][0]["engine_id"] == "hermes-agent"
    assert body["engine_runs"][0]["status"] == "running"


def test_task_plan_rejects_unregistered_operations_before_database(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(
        tasks_module,
        "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Database must not be called")),
    )
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/plan",
            json={"steps": [{
                "step_key": "unsafe_step",
                "title": "Unsafe operation",
                "input": {"operation": "shell.exec", "command": "id"},
            }]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "unregistered operation" in response.json()["detail"]
