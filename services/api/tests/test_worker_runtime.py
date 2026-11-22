import logging
from threading import Event
from uuid import UUID

import pytest

from app.services.task_worker import ClaimedStep
from app.worker_runtime import WorkerRuntime, dispatch, text_analyze


def make_step(input_data):
    return ClaimedStep(
        step_id=UUID("00000000-0000-0000-0000-000000000001"),
        task_id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        step_key="analyze",
        title="Analyze text",
        description="",
        input=input_data,
        attempt_count=1,
        max_attempts=3,
        lease_token=UUID("00000000-0000-0000-0000-000000000004"),
        lease_expires_at="2026-11-20T12:00:00+00:00",
    )


def stub_hermes_context(monkeypatch):
    """Keep lifecycle tests independent from DB-backed context and skill queries."""
    import app.worker_runtime as runtime_module

    monkeypatch.setattr(
        runtime_module, "_hermes_task_scope",
        lambda _step: {"project_id": None, "conversation_id": None},
    )
    monkeypatch.setattr(runtime_module, "_hermes_approved_skills", lambda _step: [])
    # State stores only retain this client in these tests; no DB methods are invoked.
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())


def test_text_analyze_returns_bounded_deterministic_metrics():
    result = dispatch(make_step({"operation": "text.analyze", "text": "one two\nthree"}))
    assert result["word_count"] == 3
    assert result["character_count"] == 13
    assert result["line_count"] == 2


def test_worker_rejects_unregistered_operations():
    with pytest.raises(ValueError, match="unsupported_operation"):
        dispatch(make_step({"operation": "shell.exec", "command": "whoami"}))


def test_text_analyze_requires_string_input():
    with pytest.raises(ValueError, match="requires a string"):
        text_analyze(make_step({"operation": "text.analyze", "text": 123}))


def test_runtime_stops_without_claiming_work_after_stop_signal():
    class NeverCalledWorker:
        def run_once(self, _handler):
            raise AssertionError("stop should be checked before the first iteration")

    stop = Event()
    stop.set()
    runtime = WorkerRuntime(NeverCalledWorker())
    runtime.run(stop)


def test_runtime_rejects_unsafe_poll_intervals():
    with pytest.raises(ValueError):
        WorkerRuntime(object(), poll_interval_seconds=0)


from types import SimpleNamespace

from app.services.task_worker import TaskWorker


class _RpcSequence:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def rpc(self, name, args):
        self.calls.append((name, args))
        value = self.responses.pop(0)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=value))


STEP_DATA = {
    "step_id": "00000000-0000-0000-0000-000000000001",
    "task_id": "00000000-0000-0000-0000-000000000002",
    "user_id": "00000000-0000-0000-0000-000000000003",
    "step_key": "analyze_text",
    "title": "Analyze supplied text",
    "description": "",
    "input": {"operation": "text.analyze", "text": "SULY agent runtime"},
    "attempt_count": 1,
    "max_attempts": 3,
    "lease_token": "00000000-0000-0000-0000-000000000004",
    "lease_expires_at": "2026-11-20T12:00:00+00:00",
}


def test_planned_step_executes_through_claim_dispatch_and_checkpoint():
    rpc = _RpcSequence([STEP_DATA, True, True])
    worker = TaskWorker(rpc, "integration-test-worker")

    result = worker.run_once(dispatch)

    assert result == "completed"
    assert [call[0] for call in rpc.calls] == [
        "claim_task_step",
        "renew_task_step_lease",
        "complete_task_step",
    ]
    committed = rpc.calls[2][1]["p_output"]
    assert committed["operation"] == "text.analyze"
    assert committed["word_count"] == 3
    assert committed["character_count"] == len("SULY agent runtime")


def test_unsupported_planned_operation_is_failed_not_completed():
    rpc = _RpcSequence([
        {**STEP_DATA, "input": {"operation": "shell.exec", "command": "unsafe"}},
        True,
        {"accepted": True, "step_status": "pending"},
    ])
    worker = TaskWorker(rpc, "integration-test-worker")

    result = worker.run_once(dispatch)

    assert result == "failed_or_retry_scheduled"
    assert rpc.calls[-1][0] == "fail_task_step"
    assert rpc.calls[-1][1]["p_error_code"] == "tool_execution_failed"



def test_worker_does_not_persist_raw_handler_exception_details():
    secret_like_detail = "provider-key=do-not-store-this"
    rpc = _RpcSequence([
        STEP_DATA,
        True,
        {"accepted": True, "step_status": "pending"},
    ])
    worker = TaskWorker(rpc, "redaction-test-worker")

    def failing_handler(_step):
        raise RuntimeError(secret_like_detail)

    result = worker.run_once(failing_handler)

    assert result == "failed_or_retry_scheduled"
    failure_args = rpc.calls[-1][1]
    assert failure_args["p_error_code"] == "tool_execution_failed"
    assert secret_like_detail not in failure_args["p_error_message"]
    assert "Sensitive diagnostic details were not stored" in failure_args["p_error_message"]


def test_worker_does_not_complete_when_handler_output_is_not_object():
    rpc = _RpcSequence([
        STEP_DATA,
        True,
        {"accepted": True, "step_status": "pending"},
    ])
    worker = TaskWorker(rpc, "invalid-output-worker")

    result = worker.run_once(lambda _step: ["not", "an", "object"])

    assert result == "failed_or_retry_scheduled"
    assert rpc.calls[-1][0] == "fail_task_step"
    assert all(call[0] != "complete_task_step" for call in rpc.calls)



@pytest.mark.parametrize("invalid_claim, expected_error", [
    ("not-an-object", "worker_claim_invalid_payload"),
    ({**STEP_DATA, "input": ["not", "an", "object"]}, "worker_claim_invalid_input"),
    ({**STEP_DATA, "attempt_count": 0}, "worker_claim_invalid_attempt_bounds"),
    ({**STEP_DATA, "max_attempts": 11}, "worker_claim_invalid_attempt_bounds"),
    ({**STEP_DATA, "step_key": "x" * 101}, "worker_claim_invalid_step_metadata"),
])
def test_worker_rejects_malformed_claim_payloads(invalid_claim, expected_error):
    rpc = _RpcSequence([invalid_claim])
    worker = TaskWorker(rpc, "malformed-claim-worker")

    with pytest.raises(ValueError, match=expected_error):
        worker.claim()


def test_ai_provider_task_requires_persisted_approval_scope():
    step = make_step({"operation": "ai.respond", "prompt": "hello"})
    with pytest.raises(PermissionError, match="tool_approval_required:ai.provider.run"):
        dispatch(step)


def test_ai_provider_task_calls_gateway_only_after_approval(monkeypatch):
    import app.worker_runtime as runtime_module

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"ai.provider.run"})

    async def fake_generate_reply(messages):
        assert messages == [{"role": "user", "content": "safe task"}]
        return "AI response"

    monkeypatch.setattr(runtime_module, "generate_reply", fake_generate_reply)
    result = dispatch(make_step({"operation": "ai.respond", "prompt": "safe task"}), ApprovedScopes())
    assert result == {"operation": "ai.respond", "content": "AI response"}


def test_hermes_agent_task_requires_persisted_approval_scope():
    step = make_step({"operation": "hermes.agent.turn", "prompt": "hello"})
    with pytest.raises(PermissionError, match="tool_approval_required:agent.hermes.run"):
        dispatch(step)


class FakeEngineRunStore:
    def __init__(self, *_args):
        self.events = []
    def start(self, step, engine_id):
        self.events.append(("start", step.step_id, engine_id))
        return UUID("00000000-0000-0000-0000-000000000099")
    def attach_upstream_run_id(self, run_id, step, upstream_run_id):
        self.events.append(("attach", run_id, step.step_id, upstream_run_id))
        return True
    def attach_runtime_id(self, run_id, step, runtime_id):
        self.events.append(("runtime", run_id, step.step_id, runtime_id))
        return True
    def append_event(self, run_id, step, event):
        self.events.append(("event", run_id, step.step_id, dict(event)))
        return True
    def finish(self, run_id, step, status, error_code=None):
        self.events.append(("finish", run_id, step.step_id, status, error_code))
        return True


class FakeRuntimeBroker:
    def __init__(self):
        self.acquired = []
        self.acquired_files = []
        self.acquired_skills = []
        self.released = []

    def acquire(self, task_id, engine_run_id, engine_id, *, files=None, skills=None):
        from types import SimpleNamespace
        lease = SimpleNamespace(
            task_id=task_id,
            engine_run_id=engine_run_id,
            engine_id=engine_id,
            runtime_id="00000000-0000-0000-0000-000000000055",
        )
        self.acquired.append(lease)
        self.acquired_files.append(files)
        self.acquired_skills.append(skills)
        return lease

    def release(self, lease):
        self.released.append(lease)
        return True


def test_hermes_task_scope_rejects_a_task_not_owned_by_the_claimed_user(monkeypatch):
    import app.worker_runtime as runtime_module

    step = make_step({"operation": "hermes.agent.turn", "prompt": "safe"})
    filters = []

    class Query:
        def select(self, *_args):
            return self
        def eq(self, key, value):
            filters.append((key, value))
            return self
        def limit(self, _value):
            return self
        def execute(self):
            return SimpleNamespace(data=[])

    class Client:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def table(self, name):
            assert name == "tasks"
            return Query()

    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: Client())
    with pytest.raises(PermissionError, match="hermes_task_owner_mismatch"):
        runtime_module._hermes_task_scope(step)

    assert filters == [
        ("id", str(step.task_id)),
        ("user_id", str(step.user_id)),
    ]


def test_hermes_prompt_loads_only_owner_scoped_prior_conversation_messages(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    step = make_step({"operation": "hermes.agent.turn", "prompt": "current request"})
    calls = []

    class Query:
        def __init__(self, table):
            self.table_name = table
        def select(self, *_args): return self
        def eq(self, key, value):
            calls.append((self.table_name, "eq", key, value))
            return self
        def in_(self, key, value):
            calls.append((self.table_name, "in", key, value))
            return self
        def lte(self, key, value):
            calls.append((self.table_name, "lte", key, value))
            return self
        def order(self, *_args, **_kwargs): return self
        def limit(self, *_args): return self
        def execute(self):
            if self.table_name == "tasks":
                return SimpleNamespace(data=[{
                    "conversation_id": "conversation-1",
                    "created_at": "2026-11-21T10:00:00Z",
                }])
            return SimpleNamespace(data=[
                {"role": "assistant", "content": "Earlier assistant reply"},
                {"role": "user", "content": "Earlier user message"},
                {"role": "system", "content": "must not include system rows"},
                {"role": "tool", "content": "must not include tool rows"},
            ])

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def table(self, name): return Query(name)

    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: Client())
    prompt = runtime_module._hermes_prompt_with_conversation_context(step, "current request")

    assert "Earlier assistant reply" in prompt
    assert "Earlier user message" in prompt
    assert "must not include system rows" not in prompt
    assert "must not include tool rows" not in prompt
    assert "current request" in prompt
    assert ("messages", "eq", "user_id", str(step.user_id)) in calls
    assert ("messages", "eq", "conversation_id", "conversation-1") in calls
    assert ("messages", "lte", "created_at", "2026-11-21T10:00:00Z") in calls
    assert ("messages", "in", "role", ["user", "assistant"]) in calls


def test_hermes_prompt_context_is_bounded_by_current_request_size(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    step = make_step({"operation": "hermes.agent.turn", "prompt": "x" * 19_900})
    class Query:
        def __init__(self, table): self.table_name = table
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def in_(self, *_args): return self
        def lte(self, *_args): return self
        def order(self, *_args, **_kwargs): return self
        def limit(self, *_args): return self
        def execute(self):
            return SimpleNamespace(data=(
                [{"conversation_id": "conversation-1", "created_at": "2026-11-21T10:00:00Z"}]
                if self.table_name == "tasks"
                else [{"role": "user", "content": "z" * 8000}]
            ))
    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def table(self, name): return Query(name)
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: Client())
    result = runtime_module._hermes_prompt_with_conversation_context(step, "x" * 19_900)
    assert len(result) <= 20_000
    assert result.endswith("x" * 19_900)


def test_hermes_project_workspace_is_materialized_in_its_task_runtime(monkeypatch):
    import hashlib
    import app.worker_runtime as runtime_module
    monkeypatch.setattr(runtime_module, "_hermes_approved_skills", lambda _step: [])
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    class Query:
        def __init__(self, table): self.table_name = table
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def order(self, *_args, **_kwargs): return self
        def limit(self, *_args): return self
        def execute(self):
            if self.table_name == "tasks":
                return SimpleNamespace(data=[{
                    "project_id": "00000000-0000-0000-0000-000000000066",
                    "conversation_id": None,
                    "created_at": "2026-11-21T10:00:00Z",
                }])
            if self.table_name == "projects":
                return SimpleNamespace(data=[{"id": "00000000-0000-0000-0000-000000000066"}])
            if self.table_name == "project_files":
                return SimpleNamespace(data=[{
                    "path": "README.md",
                    "content": "# SULY Project",
                    "size_bytes": 13,
                    "updated_at": "2026-11-21T09:00:00Z",
                }])
            raise AssertionError("unexpected table")
    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def table(self, name): return Query(name)

    store = FakeEngineRunStore()
    broker = FakeRuntimeBroker()
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: Client())
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: {
        "engine": "hermes-agent", "content": "project inspected",
    })
    result = runtime_module.hermes_agent_turn(
        make_step({"operation": "hermes.agent.turn", "prompt": "Inspect this project"}),
        ToolExecutionContext(engine_run_store=store, runtime_broker=broker),
    )
    assert result["content"] == "project inspected"
    assert broker.acquired_files == [[{
        "path": "README.md",
        "content": "# SULY Project",
        "sha256": hashlib.sha256(b"# SULY Project").hexdigest(),
    }]]


def test_hermes_agent_task_calls_bridge_only_after_approval(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(
        runtime_module,
        "run_agent_turn",
        lambda prompt, **_kwargs: {"engine": "hermes-agent", "content": f"processed: {prompt}"},
    )
    result = dispatch(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe task"}),
        ApprovedScopes(),
        runtime_broker=FakeRuntimeBroker(),
    )
    assert result == {
        "operation": "hermes.agent.turn",
        "engine": "hermes-agent",
        "content": "processed: safe task",
        "handoff_context": "processed: safe task",
    }


def test_hermes_agent_operation_is_registered_with_approval_and_bounded_fields():
    from app.worker_runtime import TOOL_REGISTRY

    definition = TOOL_REGISTRY.get("hermes.agent.turn")
    assert definition is not None
    assert definition.permission_scope == "agent.hermes.run"
    assert definition.requires_approval is True
    assert definition.allowed_input_fields == frozenset({"prompt", "runtime_budget_seconds"})
    assert definition.required_input_fields == frozenset({"prompt"})
    assert definition.max_input_bytes <= 20_200
    assert definition.max_output_bytes <= 52_000
    assert definition.supports_cancellation is True


def test_cancel_aware_dispatch_refuses_to_start_after_cancellation():
    from app.worker_runtime import dispatch_cancel_aware

    cancelled = Event()
    cancelled.set()
    step = make_step({"operation": "text.analyze", "text": "must not execute"})
    with pytest.raises(RuntimeError, match="task_execution_cancelled"):
        dispatch_cancel_aware(step, cancelled)


def test_hermes_operation_routes_through_registry_after_approval(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda prompt, **_kwargs: {
        "engine": "hermes-agent", "content": f"processed: {prompt}",
    })
    result = dispatch(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe task"}),
        ApprovedScopes(),
        runtime_broker=FakeRuntimeBroker(),
    )
    assert result == {
        "operation": "hermes.agent.turn",
        "engine": "hermes-agent",
        "content": "processed: safe task",
        "handoff_context": "processed: safe task",
    }


def test_hermes_engine_stays_disabled_without_feature_flag(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=False,
        hermes_agent_enabled=False, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)
    with pytest.raises(RuntimeError, match="hermes_task_runtime_unavailable"):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "hello"})
        )


def test_cancel_aware_dispatch_passes_event_to_hermes_adapter(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace

    cancel_event = Event()
    received = {}

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)

    def fake_run(prompt, **kwargs):
        received["prompt"] = prompt
        received.update(kwargs)
        return {"engine": "hermes-agent", "content": "cancel-aware"}

    monkeypatch.setattr(runtime_module, "run_agent_turn", fake_run)
    result = runtime_module.dispatch_cancel_aware(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe task"}),
        cancel_event,
        ApprovedScopes(),
        runtime_broker=FakeRuntimeBroker(),
    )

    assert result["content"] == "cancel-aware"
    assert received["prompt"] == "safe task"
    assert received["cancel_event"] is cancel_event
    assert received["timeout_seconds"] == 90


def test_hermes_run_is_recorded_as_succeeded(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: {
        "engine": "hermes-agent", "content": "finished",
    })
    step = make_step({"operation": "hermes.agent.turn", "prompt": "safe"})
    result = runtime_module.hermes_agent_turn(
        step, ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
    )
    assert result["content"] == "finished"
    assert store.events[0][0] == "start"
    assert store.events[1][0] == "runtime"
    assert store.events[1][3] == "00000000-0000-0000-0000-000000000055"
    assert store.events[2][0] == "finish"
    assert store.events[2][3] == "succeeded"
    assert store.events[0][2] == "hermes-agent"
    assert store.events[1][2] == store.events[0][1]


def test_hermes_run_is_not_marked_succeeded_when_runtime_release_is_unconfirmed(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    class UnconfirmedReleaseBroker(FakeRuntimeBroker):
        def release(self, lease):
            self.released.append(lease)
            return False

    store = FakeEngineRunStore()
    broker = UnconfirmedReleaseBroker()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: {
        "engine": "hermes-agent", "content": "finished",
    })
    with pytest.raises(RuntimeError, match="hermes_runtime_cleanup_pending"):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store, runtime_broker=broker),
        )
    assert broker.released
    assert not any(event[0] == "finish" for event in store.events)


def test_hermes_run_records_failure_without_raw_error(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("sensitive prompt and upstream response")
    ))
    with pytest.raises(RuntimeError):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
        )
    assert store.events[2][3] == "failed"
    assert store.events[2][4] == "engine_execution_failed"


def test_hermes_run_records_cooperative_cancellation(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.hermes_agent import HermesAgentCancelled
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        HermesAgentCancelled("cancelled")
    ))
    with pytest.raises(HermesAgentCancelled):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
        )
    assert store.events[2][3] == "cancelled"


def test_agent_catalog_contains_roles_but_keeps_unavailable_agents_disabled(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.engine_registry import EngineDefinition, EngineRegistry

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=False,
        hermes_agent_enabled=False,
    ))
    engines = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes Agent",
            capabilities=frozenset({"agent.general"}),
            enabled=False,
        )
    ])
    manager = runtime_module.build_agent_manager(engines)
    roles = {agent.agent_id: agent for agent in manager.list()}
    assert set(roles) == {
        "general-agent", "coding-agent", "research-agent",
        "browser-agent", "workflow-agent",
    }
    assert all(not agent.enabled for agent in roles.values())


def test_agent_catalog_enables_only_configured_general_agent(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.engine_registry import EngineDefinition, EngineRegistry

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
    ))
    engines = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes Agent",
            capabilities=frozenset({"agent.general"}),
            enabled=True,
        )
    ])
    manager = runtime_module.build_agent_manager(engines)
    route = manager.route("general-agent", "agent.general")
    assert [engine.engine_id for engine in route.engines] == ["hermes-agent"]
    with pytest.raises(RuntimeError, match="agent_disabled"):
        manager.route("coding-agent", "code.edit")


def test_worker_builds_all_pinned_engines_but_only_enables_configured_hermes(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    registry = runtime_module.build_engine_registry(
        Event(),
        idempotency_key="suly-engine-catalog-test",
        on_run_started=lambda _run_id: True,
        runtime_lease=SimpleNamespace(engine_run_id="00000000-0000-0000-0000-000000000099"),
    )

    assert {engine.engine_id for engine in registry.list()} == {
        "hermes-agent", "opencode", "browser-use",
    }
    assert registry.get("hermes-agent").enabled is True
    assert registry.get("hermes-agent").adapter is not None
    assert registry.get("opencode").enabled is False
    assert registry.get("opencode").adapter is None
    assert registry.get("browser-use").enabled is False
    assert registry.get("browser-use").adapter is None


def test_worker_keeps_every_engine_disabled_when_worker_flag_is_off(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=False,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
    ))
    registry = runtime_module.build_engine_registry(
        Event(),
        idempotency_key="suly-engine-disabled-test",
        on_run_started=lambda _run_id: True,
    )
    assert all(not engine.enabled for engine in registry.list())


def test_hermes_execution_is_routed_through_agent_manager(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    selected = []
    class Route:
        engines = [SimpleNamespace(engine_id="hermes-agent")]
    class Manager:
        def route(self, agent_id, capability):
            selected.append((agent_id, capability))
            return Route()

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "build_agent_manager", lambda _registry: Manager())
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: {
        "engine": "hermes-agent", "content": "agent routed",
    })
    result = runtime_module.hermes_agent_turn(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
        ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
    )
    assert result["content"] == "agent routed"
    assert selected == [("general-agent", "agent.general")]


def test_worker_runtime_runs_optional_reconciler_before_claiming_tasks():
    class NeverClaimWorker:
        def run_once(self, _handler, *, cancel_aware_handler=None):
            stop.set()
            return "idle"

    class Reconciler:
        def __init__(self):
            self.calls = 0
        def run_once(self):
            self.calls += 1
            return 1

    stop = Event()
    reconciler = Reconciler()
    runtime = WorkerRuntime(
        NeverClaimWorker(),
        reconciler=reconciler,
        reconcile_interval_seconds=10,
    )
    runtime.run(stop)
    assert reconciler.calls == 1


def test_worker_runtime_validates_reconciliation_interval():
    with pytest.raises(ValueError, match="reconcile interval"):
        WorkerRuntime(object(), reconcile_interval_seconds=5)


def test_hermes_engine_requires_task_scoped_runtime_broker(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=False,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    store = FakeEngineRunStore()
    with pytest.raises(RuntimeError, match="hermes_task_runtime_unavailable"):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store),
        )
    assert store.events == []



def test_hermes_adapter_forwards_metadata_event_callback(monkeypatch):
    import app.worker_runtime as runtime_module
    from app.services.engine_contract import EngineRequest

    received = {}
    def callback(_event):
        return None

    def fake_run(prompt, **kwargs):
        received.update(kwargs)
        return {"engine": "hermes-agent", "content": "safe result"}

    monkeypatch.setattr(runtime_module, "run_agent_turn", fake_run)
    adapter = runtime_module.HermesAgentAdapter(
        Event(),
        idempotency_key="suly-test-event-callback",
        on_run_started=lambda _run_id: True,
        on_event=callback,
        runtime_lease=SimpleNamespace(engine_run_id="00000000-0000-0000-0000-000000000099"),
    )
    result = adapter.execute(EngineRequest(
        task_id="00000000-0000-0000-0000-000000000001",
        capability="agent.general",
        input_payload={"prompt": "safe task"},
        timeout_seconds=30,
    ))
    assert result.output["content"] == "safe result"
    assert received["on_event"] is callback



def test_hermes_agent_turn_persists_metadata_events_and_never_logs_payload(monkeypatch, caplog):
    import logging
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.engine_contract import EngineResult
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    callbacks = {}

    class Registry:
        def candidates(self, capability):
            from types import SimpleNamespace
            return [SimpleNamespace(engine_id="hermes-agent")] if capability == "agent.general" else []

        def execute(self, _engine_id, _request):
            from app.services.hermes_agent import _safe_run_event
            safe_event = _safe_run_event({
                "run_id": "run_native_123",
                "event": "tool.started",
                "seq": 7,
                "command": "sensitive command must not be stored",
            }, "run_native_123")
            callbacks["on_event"](safe_event)
            return EngineResult(engine_id="hermes-agent", output={
                "engine": "hermes-agent",
                "content": "safe output",
            })

    class Manager:
        def route(self, *_args):
            return SimpleNamespace(engines=[SimpleNamespace(engine_id="hermes-agent")])

    def registry_factory(*_args, **kwargs):
        callbacks["on_event"] = kwargs["on_event"]
        return Registry()

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "build_engine_registry", registry_factory)
    monkeypatch.setattr(runtime_module, "build_agent_manager", lambda _registry: Manager())
    caplog.set_level(logging.WARNING, logger="suly.worker")

    result = runtime_module.hermes_agent_turn(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
        ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
    )

    assert result["content"] == "safe output"
    saved = [entry for entry in store.events if entry[0] == "event"]
    assert len(saved) == 1
    assert saved[0][3] == {"event": "tool.started", "seq": 7}
    assert "sensitive command" not in caplog.text


def test_hermes_agent_turn_logs_only_metadata_when_event_persistence_fails(monkeypatch, caplog):
    import logging
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.engine_contract import EngineResult
    from app.services.tool_registry import ToolExecutionContext

    class FailingStore(FakeEngineRunStore):
        def append_event(self, *_args):
            raise RuntimeError("secret database password must not be logged")

    store = FailingStore()
    callbacks = {}

    class Registry:
        def candidates(self, capability):
            from types import SimpleNamespace
            return [SimpleNamespace(engine_id="hermes-agent")] if capability == "agent.general" else []

        def execute(self, _engine_id, _request):
            callbacks["on_event"]({"event": "approval.request", "seq": 8})
            return EngineResult(engine_id="hermes-agent", output={
                "engine": "hermes-agent",
                "content": "safe output",
            })

    class Manager:
        def route(self, *_args):
            return SimpleNamespace(engines=[SimpleNamespace(engine_id="hermes-agent")])

    def registry_factory(*_args, **kwargs):
        callbacks["on_event"] = kwargs["on_event"]
        return Registry()

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "build_engine_registry", registry_factory)
    monkeypatch.setattr(runtime_module, "build_agent_manager", lambda _registry: Manager())
    caplog.set_level(logging.WARNING, logger="suly.worker")

    result = runtime_module.hermes_agent_turn(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
        ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
    )
    assert result["content"] == "safe output"
    assert "persistence failed" in caplog.text
    assert "approval.request" in caplog.text
    assert "secret database password" not in caplog.text

def test_runtime_does_not_log_exception_messages_or_tracebacks(caplog):
    secret_text = "sensitive-provider-payload-and-database-password"

    class FailingWorker:
        def run_once(self, _handler, *, cancel_aware_handler=None):
            stop.set()
            raise RuntimeError(secret_text)

    stop = Event()
    runtime = WorkerRuntime(FailingWorker())
    with caplog.at_level(logging.ERROR, logger="suly.worker"):
        runtime.run(stop)

    assert "Worker iteration failed" in caplog.text
    assert "RuntimeError" in caplog.text
    assert secret_text not in caplog.text




def test_opencode_worker_operation_is_registered_but_disabled_by_default(monkeypatch):
    from types import SimpleNamespace
    import app.worker_runtime as runtime
    from app.services.tool_registry import ToolExecutionContext
    from app.worker_runtime import TOOL_REGISTRY

    tool = TOOL_REGISTRY.get("opencode.task.run")
    assert tool is not None
    assert tool.requires_approval is True
    assert tool.supports_cancellation is True
    assert tool.permission_scope == "engine.opencode.run"

    monkeypatch.setattr(runtime, "get_settings", lambda: SimpleNamespace(
        worker_enabled=False,
        opencode_enabled=False,
    ))
    step = make_step({
        "operation": "opencode.task.run",
        "project_id": "00000000-0000-0000-0000-000000000099",
        "prompt": "Create a feature",
    })
    fake_broker = SimpleNamespace(run_task=lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Disabled OpenCode must not contact runtime")
    ))
    fake_store = SimpleNamespace(start=lambda *_args: (_ for _ in ()).throw(
        AssertionError("Disabled OpenCode must not create an engine run")
    ))
    with pytest.raises(RuntimeError, match="disabled_or_unavailable"):
        runtime.opencode_task_run(step, ToolExecutionContext(
            approved_scopes=frozenset({"engine.opencode.run"}),
            cancel_event=Event(),
            engine_run_store=fake_store,
            runtime_broker=fake_broker,
        ))



def test_opencode_worker_handler_returns_review_ids_and_finishes_engine_run(monkeypatch):
    from types import SimpleNamespace
    from uuid import UUID
    import app.worker_runtime as runtime
    from app.services.tool_registry import ToolExecutionContext

    project_id = "00000000-0000-0000-0000-000000000099"
    engine_run_id = UUID("00000000-0000-0000-0000-000000000088")
    finishes = []

    class FakeEngineRunStore:
        def start(self, step, engine):
            assert engine == "opencode"
            assert step.input["operation"] == "opencode.task.run"
            return engine_run_id
        def finish(self, run_id, step, status, error_code=None):
            finishes.append((run_id, status, error_code))
            return True

    class FakeExecutor:
        def __init__(self, **kwargs):
            assert kwargs["runtime_broker"] is not None
        def execute(self, **kwargs):
            assert kwargs["user_id"] == str(step.user_id)
            assert kwargs["project_id"] == project_id
            assert kwargs["engine_run_id"] == str(engine_run_id)
            assert kwargs["prompt"] == "Build a feature"
            return {
                "task_run": {"id": "opencode-run", "status": "review_ready"},
                "session": {"id": "session-record"},
                "change_set": {"id": "change-set"},
                "changes": {"changed_count": 2},
            }

    monkeypatch.setattr(runtime, "get_settings", lambda: SimpleNamespace(worker_enabled=True, opencode_enabled=True))
    monkeypatch.setattr(runtime, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime, "OpenCodeTaskExecutor", FakeExecutor)
    dispatch_calls = []
    original_dispatch_execute = runtime.EngineDispatcher.execute
    def observe_dispatch(self, request, *, preferred_engine_ids=()):
        dispatch_calls.append((request.capability, tuple(preferred_engine_ids)))
        return original_dispatch_execute(self, request, preferred_engine_ids=preferred_engine_ids)
    monkeypatch.setattr(runtime.EngineDispatcher, "execute", observe_dispatch)
    step = make_step({
        "operation": "opencode.task.run",
        "project_id": project_id,
        "prompt": "Build a feature",
        "title": "Feature task",
    })
    result = runtime.opencode_task_run(step, ToolExecutionContext(
        approved_scopes=frozenset({"engine.opencode.run"}),
        cancel_event=Event(),
        engine_run_store=FakeEngineRunStore(),
        runtime_broker=object(),
    ))
    assert result == {
        "operation": "opencode.task.run",
        "engine": "opencode",
        "engine_run_id": str(engine_run_id),
        "opencode_run_id": "opencode-run",
        "session_record_id": "session-record",
        "change_set_id": "change-set",
        "status": "review_ready",
        "changed_count": 2,
        "requires_review": True,
        "handoff_context": "OpenCode prepared change set change-set with 2 changed files; human review is required.",
    }
    assert dispatch_calls == [("code.edit", ("opencode",))]
    assert finishes == [(engine_run_id, "succeeded", None)]


def test_hermes_delegated_runtime_budget_reaches_native_runs_adapter(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True,
        hermes_agent_enabled=True,
        hermes_agent_isolation_confirmed=True,
        hermes_agent_base_url="http://hermes:8642",
        hermes_agent_api_key=object(),
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    seen = {}
    def fake_run(prompt, **kwargs):
        seen.update(kwargs)
        return {"engine": "hermes-agent", "content": "bounded"}

    monkeypatch.setattr(runtime_module, "run_agent_turn", fake_run)
    runtime_module.hermes_agent_turn(
        make_step({
            "operation": "hermes.agent.turn",
            "prompt": "bounded delegated task",
            "runtime_budget_seconds": 120,
        }),
        context=runtime_module.ToolExecutionContext(
            approved_scopes=frozenset({"agent.hermes.run"}),
            runtime_broker=FakeRuntimeBroker(),
            engine_run_store=FakeEngineRunStore(),
        ),
    )
    assert seen["timeout_seconds"] == 120


def test_hermes_rejects_runtime_budget_above_native_runs_limit(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True, hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    with pytest.raises(ValueError, match="hermes_runtime_budget_invalid"):
        runtime_module.hermes_agent_turn(
            make_step({
                "operation": "hermes.agent.turn",
                "prompt": "unsafe budget",
                "runtime_budget_seconds": 301,
            }),
            context=SimpleNamespace(
                runtime_broker=FakeRuntimeBroker(),
                engine_run_store=FakeEngineRunStore(),
                cancel_event=None,
            ),
        )


def test_hermes_terminal_approval_callback_uses_suly_gateway(monkeypatch):
    import app.worker_runtime as runtime_module
    stub_hermes_context(monkeypatch)
    from types import SimpleNamespace
    from app.services.engine_contract import EngineResult
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    callbacks = {}
    gateway_calls = []
    approval_responses = []

    class Gateway:
        def __init__(self, _client):
            pass

        def authorize_upstream_tool_approval(self, **kwargs):
            gateway_calls.append(kwargs)
            return True

    class Registry:
        def candidates(self, capability):
            from types import SimpleNamespace
            return [SimpleNamespace(engine_id="hermes-agent")] if capability == "agent.general" else []

        def execute(self, _engine_id, _request):
            assert callbacks["run_started"]("run_native_approval_123") is True
            callbacks["event"]({
                "event": "approval.request",
                "approval_request_id": "approval_req_123456",
                "tool_id": "terminal",
            })
            return EngineResult(engine_id="hermes-agent", output={
                "engine": "hermes-agent", "content": "completed after approved tool",
            })

    class Manager:
        def route(self, *_args):
            return SimpleNamespace(engines=[SimpleNamespace(engine_id="hermes-agent")])

    def registry_factory(*_args, **kwargs):
        callbacks["event"] = kwargs["on_event"]
        callbacks["run_started"] = kwargs["on_run_started"]
        return Registry()

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True, hermes_agent_enabled=True, agent_memory_enabled=False,
        hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "_hermes_project_workspace_files", lambda _step: None)
    monkeypatch.setattr(runtime_module, "HermesToolGateway", Gateway)
    monkeypatch.setattr(runtime_module, "build_engine_registry", registry_factory)
    monkeypatch.setattr(runtime_module, "build_agent_manager", lambda _registry: Manager())
    monkeypatch.setattr(runtime_module, "respond_run_approval", lambda **kwargs: approval_responses.append(kwargs) or True)

    result = runtime_module.hermes_agent_turn(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe prompt"}),
        ToolExecutionContext(engine_run_store=store, runtime_broker=FakeRuntimeBroker()),
    )

    assert result["content"] == "completed after approved tool"
    assert gateway_calls == [{
        "user_id": str(make_step({}).user_id),
        "task_id": str(make_step({}).task_id),
        "step_id": str(make_step({}).step_id),
        "lease_token": str(make_step({}).lease_token),
        "tool_id": "terminal",
        "request_id": "approval_req_123456",
    }]
    assert len(approval_responses) == 1
    assert approval_responses[0]["choice"] == "once"
    assert approval_responses[0]["request_id"] == "approval_req_123456"
