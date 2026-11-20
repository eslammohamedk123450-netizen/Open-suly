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
    def finish(self, run_id, step, status, error_code=None):
        self.events.append(("finish", run_id, step.step_id, status, error_code))
        return True


def test_hermes_agent_task_calls_bridge_only_after_approval(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
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
    )
    assert result == {
        "operation": "hermes.agent.turn",
        "engine": "hermes-agent",
        "content": "processed: safe task",
    }


def test_hermes_agent_operation_is_registered_with_approval_and_bounded_fields():
    from app.worker_runtime import TOOL_REGISTRY

    definition = TOOL_REGISTRY.get("hermes.agent.turn")
    assert definition is not None
    assert definition.permission_scope == "agent.hermes.run"
    assert definition.requires_approval is True
    assert definition.allowed_input_fields == frozenset({"prompt"})
    assert definition.required_input_fields == frozenset({"prompt"})
    assert definition.max_input_bytes <= 20_100
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
    from types import SimpleNamespace

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda prompt, **_kwargs: {
        "engine": "hermes-agent", "content": f"processed: {prompt}",
    })
    result = dispatch(
        make_step({"operation": "hermes.agent.turn", "prompt": "safe task"}),
        ApprovedScopes(),
    )
    assert result == {
        "operation": "hermes.agent.turn",
        "engine": "hermes-agent",
        "content": "processed: safe task",
    }


def test_hermes_engine_stays_disabled_without_feature_flag(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=False, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "get_supabase_admin_client", lambda: object())
    monkeypatch.setattr(runtime_module, "EngineRunStore", FakeEngineRunStore)
    with pytest.raises(RuntimeError, match="engine_disabled"):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "hello"})
        )


def test_cancel_aware_dispatch_passes_event_to_hermes_adapter(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace

    cancel_event = Event()
    received = {}

    class ApprovedScopes:
        def active_scopes(self, _user_id):
            return frozenset({"agent.hermes.run"})

    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
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
    )

    assert result["content"] == "cancel-aware"
    assert received["prompt"] == "safe task"
    assert received["cancel_event"] is cancel_event
    assert received["timeout_seconds"] == 90


def test_hermes_run_is_recorded_as_succeeded(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: {
        "engine": "hermes-agent", "content": "finished",
    })
    step = make_step({"operation": "hermes.agent.turn", "prompt": "safe"})
    result = runtime_module.hermes_agent_turn(
        step, ToolExecutionContext(engine_run_store=store),
    )
    assert result["content"] == "finished"
    assert store.events[0][0] == "start"
    assert store.events[1][0] == "finish"
    assert store.events[1][3] == "succeeded"
    assert store.events[0][2] == "hermes-agent"
    assert store.events[1][2] == store.events[0][1]


def test_hermes_run_records_failure_without_raw_error(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("sensitive prompt and upstream response")
    ))
    with pytest.raises(RuntimeError):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store),
        )
    assert store.events[1][3] == "failed"
    assert store.events[1][4] == "engine_execution_failed"


def test_hermes_run_records_cooperative_cancellation(monkeypatch):
    import app.worker_runtime as runtime_module
    from types import SimpleNamespace
    from app.services.hermes_agent import HermesAgentCancelled
    from app.services.tool_registry import ToolExecutionContext

    store = FakeEngineRunStore()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        hermes_agent_enabled=True, hermes_agent_timeout_seconds=90.0,
    ))
    monkeypatch.setattr(runtime_module, "run_agent_turn", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        HermesAgentCancelled("cancelled")
    ))
    with pytest.raises(HermesAgentCancelled):
        runtime_module.hermes_agent_turn(
            make_step({"operation": "hermes.agent.turn", "prompt": "safe"}),
            ToolExecutionContext(engine_run_store=store),
        )
    assert store.events[1][3] == "cancelled"
