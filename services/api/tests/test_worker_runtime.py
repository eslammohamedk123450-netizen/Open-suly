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
