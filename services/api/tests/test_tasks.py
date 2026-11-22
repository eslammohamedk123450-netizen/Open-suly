from datetime import datetime, timedelta, timezone

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


class _CreateTaskQuery:
    def __init__(self, admin, table):
        self.admin = admin
        self.table_name = table
        self.filters = {}
        self.insert_payload = None
    def select(self, *_args): return self
    def eq(self, key, value):
        self.filters[key] = value
        return self
    def limit(self, *_args): return self
    def insert(self, payload):
        self.insert_payload = payload
        return self
    def execute(self):
        if self.insert_payload is not None:
            self.admin.inserted = self.insert_payload
            return SimpleNamespace(data=[{
                **self.insert_payload,
                "id": "00000000-0000-0000-0000-000000000099",
                "status": "queued",
            }])
        if self.table_name == "tasks":
            return SimpleNamespace(data=[])
        if self.table_name == "conversations":
            owned = (
                self.filters.get("id") == self.admin.conversation_id
                and self.filters.get("user_id") == "test-user"
            )
            return SimpleNamespace(data=[{"id": self.admin.conversation_id}] if owned else [])
        raise AssertionError("unexpected table")


class _CreateTaskAdmin:
    def __init__(self, conversation_id):
        self.conversation_id = conversation_id
        self.inserted = None
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name): return _CreateTaskQuery(self, name)


def test_task_creation_persists_only_owner_matched_conversation_id(monkeypatch):
    conversation_id = "00000000-0000-0000-0000-000000000055"
    admin = _CreateTaskAdmin(conversation_id)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks", json={
            "request": "agent: continue this conversation",
            "idempotency_key": "conversation-task-01",
            "conversation_id": conversation_id,
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 202
    assert admin.inserted["conversation_id"] == conversation_id


def test_task_creation_rejects_conversation_owned_by_another_user(monkeypatch):
    admin = _CreateTaskAdmin("another-conversation")
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks", json={
            "request": "agent: private task",
            "idempotency_key": "conversation-task-02",
            "conversation_id": "00000000-0000-0000-0000-000000000055",
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert admin.inserted is None


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
            "engine_handoffs": [],
            "engine_run_events": [{
                "id": 1,
                "engine_run_id": "run-1",
                "task_id": "00000000-0000-0000-0000-000000000001",
                "event_name": "tool.started",
                "event_seq": 1,
                "event_timestamp": 1800000000.0,
                "metadata": {
                    "subagent_id": "child_01",
                    "status": "running",
                    "task_index": 0,
                    "task_count": 2,
                },
                "received_at": "2026-11-20T12:00:00Z",
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
    assert body["engine_events"][0]["event_name"] == "tool.started"
    assert body["engine_events"][0]["engine_run_id"] == "run-1"
    assert body["engine_events"][0]["metadata"]["subagent_id"] == "child_01"


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


def test_auto_plan_routes_general_agent_only_when_isolated_runtime_is_ready(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config

    admin = _FakeAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user",
        "status": "queued",
        "request": "agent: Review this task",
    })
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        runtime_provisioner_url="https://runtime-provisioner.internal",
        runtime_provisioner_token=object(),
        runtime_provisioner_allowed_origins=("https://hermes-runtime.internal:8443",),
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/auto-plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["planner"] == "agent-routing-v1"
    assert response.json()["steps"][0]["input"]["operation"] == "hermes.agent.turn"


def test_auto_plan_refuses_general_agent_without_isolation(monkeypatch):
    from types import SimpleNamespace
    import app.core.config as config

    admin = _FakeAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user",
        "status": "queued",
        "request": "agent: Review this task",
    })
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=False,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        runtime_provisioner_url=None,
        runtime_provisioner_token=None,
        runtime_provisioner_allowed_origins=(),
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/auto-plan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert admin.rpc_calls == []



class _SteerQuery:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self
    def gt(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) is not None and row.get(key) > value]
        return self
    def limit(self, count):
        self.rows = self.rows[:count]
        return self
    def execute(self): return SimpleNamespace(data=self.rows)


class _SteerAdmin:
    def __init__(self):
        self.tables = {
            "tasks": [{
                "id": "00000000-0000-0000-0000-000000000001",
                "user_id": "test-user",
                "status": "running",
            }],
            "engine_runs": [{
                "id": "00000000-0000-0000-0000-000000000099",
                "task_id": "00000000-0000-0000-0000-000000000001",
                "user_id": "test-user",
                "step_id": "00000000-0000-0000-0000-000000000002",
                "engine_id": "hermes-agent",
                "status": "running",
                "upstream_run_id": "run_native_123",
                "runtime_id": "00000000-0000-0000-0000-000000000055",
            }],
            "task_steps": [{
                "id": "00000000-0000-0000-0000-000000000002",
                "task_id": "00000000-0000-0000-0000-000000000001",
                "user_id": "test-user",
                "status": "running",
                "lease_token": "00000000-0000-0000-0000-000000000004",
                "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            }],
        }
        self.rpc_calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name): return _SteerQuery(self.tables[name])
    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))



def _fake_hermes_runtime_recovery(*_args, **kwargs):
    from types import SimpleNamespace
    return SimpleNamespace(
        runtime_id=kwargs["runtime_id"],
        task_id=str(kwargs["task_id"]),
        engine_run_id=str(kwargs["engine_run_id"]),
        engine_id="hermes-agent",
    )

def test_task_owner_can_steer_only_their_active_hermes_run(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    steered = []
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "_recover_hermes_runtime", _fake_hermes_runtime_recovery)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    monkeypatch.setattr(
        tasks_module, "steer_agent_run",
        lambda upstream_id, text, **_kwargs: steered.append((upstream_id, text)) or True,
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/steer",
            json={"input": "Continue with the next safe step"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert steered == [("run_native_123", "Continue with the next safe step")]
    assert admin.rpc_calls == [("append_engine_run_event", {
        "p_run_id": "00000000-0000-0000-0000-000000000099",
        "p_step_id": "00000000-0000-0000-0000-000000000002",
        "p_lease_token": "00000000-0000-0000-0000-000000000004",
        "p_event_name": "run.steered",
        "p_event_seq": None,
        "p_event_timestamp": None,
    })]


def test_task_steering_rejects_non_running_engine_before_upstream_call(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["engine_runs"][0]["status"] = "succeeded"
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "steer_agent_run", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Upstream must not be called for a terminal run")
    ))
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/steer",
            json={"input": "Do not run"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409



def test_task_approval_cannot_resolve_request_from_another_engine_run(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000088",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "resolve_agent_approval", lambda *_args: (_ for _ in ()).throw(
        AssertionError("An approval from a different run must never be resolved")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "once"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_task_approval_details_rejects_expired_worker_lease(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    admin.tables["task_steps"][0]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat()
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_agent_approval_details", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Expired lease must not disclose approval command details")
    ))
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.get(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals/approval-req_123",
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409


def test_task_owner_can_fetch_redacted_details_for_their_pending_approval(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "_recover_hermes_runtime", _fake_hermes_runtime_recovery)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    monkeypatch.setattr(tasks_module, "get_agent_approval_details", lambda upstream_id, request_id, **_kwargs: {
        "request_id": request_id,
        "command": "git status",
        "description": "Review repository status",
    })
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.get(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals/approval-req_123",
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["command"] == "git status"
    assert response.json()["description"] == "Review repository status"
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["vary"] == "Authorization"


def test_task_approval_details_rejects_answered_or_untracked_request(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.responded",
        "approval_request_id": "approval-req_123",
    }]
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_agent_approval_details", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Answered request details must not be returned")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.get(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals/approval-req_123",
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_task_approval_resolution_rejects_expired_worker_lease(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    admin.tables["task_steps"][0]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat()
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    monkeypatch.setattr(tasks_module, "resolve_agent_approval", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Expired lease must not resolve an upstream approval")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "once"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409


def test_task_steering_rejects_expired_worker_lease(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["task_steps"][0]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).isoformat()
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    monkeypatch.setattr(tasks_module, "steer_agent_run", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Expired lease must not steer an upstream run")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/steer",
            json={"input": "Continue safely"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409


def test_task_owner_can_resolve_one_exact_hermes_approval_once(monkeypatch):
    from types import SimpleNamespace

    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    resolved = []
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "_recover_hermes_runtime", _fake_hermes_runtime_recovery)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    monkeypatch.setattr(
        tasks_module, "resolve_agent_approval",
        lambda upstream_id, request_id, choice, **_kwargs: resolved.append((upstream_id, request_id, choice)) or True,
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "once"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert resolved == [("run_native_123", "approval-req_123", "once")]
    assert admin.rpc_calls == [("append_engine_run_event", {
        "p_run_id": "00000000-0000-0000-0000-000000000099",
        "p_step_id": "00000000-0000-0000-0000-000000000002",
        "p_lease_token": "00000000-0000-0000-0000-000000000004",
        "p_event_name": "approval.responded",
        "p_event_seq": None,
        "p_event_timestamp": None,
        "p_approval_request_id": "approval-req_123",
        "p_approval_choice": "once",
    })]


def test_task_approval_rejects_persistent_choice_before_upstream_call(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [{
        "id": 1,
        "engine_run_id": "00000000-0000-0000-0000-000000000099",
        "event_name": "approval.request",
        "approval_request_id": "approval-req_123",
    }]
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "resolve_agent_approval", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Persistent grants must never reach Hermes")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "always"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_task_approval_requires_request_id_from_this_engine_run(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = []
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "resolve_agent_approval", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Untracked approval must never reach Hermes")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "deny"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_task_approval_rejects_already_answered_request(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["engine_run_events"] = [
        {
            "id": 1,
            "engine_run_id": "00000000-0000-0000-0000-000000000099",
            "event_name": "approval.request",
            "approval_request_id": "approval-req_123",
        },
        {
            "id": 2,
            "engine_run_id": "00000000-0000-0000-0000-000000000099",
            "event_name": "approval.responded",
            "approval_request_id": "approval-req_123",
        },
    ]
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "resolve_agent_approval", lambda *_args: (_ for _ in ()).throw(
        AssertionError("Answered approval must never reach Hermes")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/approvals",
            json={"request_id": "approval-req_123", "choice": "once"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409


def test_task_steering_cannot_access_another_users_task_or_run(monkeypatch):
    admin = _SteerAdmin()
    admin.tables["tasks"][0]["user_id"] = "different-user"
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "steer_agent_run", lambda *_args: (_ for _ in ()).throw(
        AssertionError("An unowned task must never reach Hermes")
    ))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post(
            "/v1/tasks/00000000-0000-0000-0000-000000000001/engine-runs/00000000-0000-0000-0000-000000000099/steer",
            json={"input": "Do not access another user's run"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404



class _ProjectCheckQuery:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self.rows)
    def insert(self, _payload):
        raise AssertionError("Task must not be inserted for a project owned by another user")


class _ProjectCheckAdmin:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name):
        return _ProjectCheckQuery([])


def test_task_creation_rejects_project_not_owned_by_user(monkeypatch):
    admin = _ProjectCheckAdmin()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-a", email=None)
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    try:
        response = client.post("/v1/tasks", json={
            "request": "Build my app",
            "idempotency_key": "project-task-0001",
            "project_id": "00000000-0000-0000-0000-000000000099",
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."



class _OpenCodePlanQuery:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self.rows)


class _OpenCodePlanRpc:
    def __init__(self, result):
        self.result = result
        self.payload = None
    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self.result)


class _OpenCodePlanAdmin:
    def __init__(self, task):
        self.task = task
        self.rpc_calls = []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, _name):
        return _OpenCodePlanQuery([self.task])
    def rpc(self, name, payload):
        call = _OpenCodePlanRpc({"task_id": payload["p_task_id"], "planned": True})
        self.rpc_calls.append((name, payload))
        return call


def test_opencode_plan_requires_task_linked_project_before_rpc(monkeypatch):
    admin = _OpenCodePlanAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user", "status": "queued",
        "project_id": None, "request": "Build an app", "title": "Build",
    })
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: type("EnabledSettings", (), {
        "worker_enabled": True, "opencode_enabled": True,
        "runtime_provisioner_url": "https://runtime.example.test",
        "runtime_provisioner_token": object(),
        "runtime_provisioner_allowed_origins": ["https://runtime.example.test"],
    })())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/opencode-plan")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert admin.rpc_calls == []


def test_opencode_plan_enqueues_registered_worker_step(monkeypatch):
    admin = _OpenCodePlanAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user", "status": "queued",
        "project_id": "00000000-0000-0000-0000-000000000099",
        "request": "Create a small feature", "title": "Feature task",
    })
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(tasks_module, "get_settings", lambda: type("EnabledSettings", (), {
        "worker_enabled": True, "opencode_enabled": True,
        "runtime_provisioner_url": "https://runtime.example.test",
        "runtime_provisioner_token": object(),
        "runtime_provisioner_allowed_origins": ["https://runtime.example.test"],
    })())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/opencode-plan")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 202
    assert response.json()["planner"] == "opencode-direct-v1"
    assert len(admin.rpc_calls) == 1
    plan = admin.rpc_calls[0][1]["p_steps"]
    assert plan[0]["input"]["operation"] == "opencode.task.run"
    assert plan[0]["input"]["project_id"] == "00000000-0000-0000-0000-000000000099"
    assert plan[0]["input"]["prompt"] == "Create a small feature"



def test_opencode_plan_rejects_disabled_runtime_before_database(monkeypatch):
    monkeypatch.setattr(tasks_module, "get_settings", lambda: type("DisabledSettings", (), {
        "worker_enabled": False, "opencode_enabled": False,
        "runtime_provisioner_url": None, "runtime_provisioner_token": None,
        "runtime_provisioner_allowed_origins": [],
    })())
    monkeypatch.setattr(
        tasks_module, "get_supabase_admin_client",
        lambda: (_ for _ in ()).throw(AssertionError("Disabled engine must not access task database")),
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/opencode-plan")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "not configured or enabled" in response.json()["detail"]


class _CancelTaskQuery:
    def __init__(self, admin, table):
        self.admin, self.table_name = admin, table
        self.filters = {}
        self.status_values = None
        self.update_payload = None
    def select(self, *_args): return self
    def eq(self, key, value):
        self.filters[key] = value
        return self
    def limit(self, *_args): return self
    def in_(self, key, values):
        self.filters[key] = values
        self.status_values = values
        return self
    def update(self, payload):
        self.update_payload = payload
        return self
    def execute(self):
        if self.update_payload is not None:
            if self.admin.task["status"] not in (self.status_values or []):
                return SimpleNamespace(data=[])
            self.admin.task.update(self.update_payload)
            return SimpleNamespace(data=[dict(self.admin.task)])
        owned = (
            self.filters.get("id") == self.admin.task["id"]
            and self.filters.get("user_id") == "test-user"
        )
        return SimpleNamespace(data=[dict(self.admin.task)] if owned else [])


class _CancelTaskAdmin:
    def __init__(self, task):
        self.task = task
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def table(self, name): return _CancelTaskQuery(self, name)


def test_parent_task_can_be_cancelled_while_waiting_for_delegated_children(monkeypatch):
    admin = _CancelTaskAdmin({
        "id": "00000000-0000-0000-0000-000000000001",
        "user_id": "test-user",
        "status": "waiting_children",
        "cancel_requested_at": None,
    })
    monkeypatch.setattr(tasks_module, "get_supabase_admin_client", lambda: admin)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="test-user", email=None)
    try:
        response = client.post("/v1/tasks/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"
    assert response.json()["cancel_requested_at"] is not None
