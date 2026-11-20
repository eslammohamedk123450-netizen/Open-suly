from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.task_worker import TaskWorker


STEP = {
    "step_id": "00000000-0000-0000-0000-000000000001",
    "task_id": "00000000-0000-0000-0000-000000000002",
    "user_id": "00000000-0000-0000-0000-000000000003",
    "step_key": "research",
    "title": "Research",
    "description": "",
    "input": {"topic": "testing"},
    "attempt_count": 1,
    "max_attempts": 3,
    "lease_token": "00000000-0000-0000-0000-000000000004",
    "lease_expires_at": "2026-11-20T12:00:00+00:00",
}


class FakeRpc:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        value = self.responses.pop(0)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=value))


def test_worker_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        TaskWorker(object(), " ")
    with pytest.raises(ValueError):
        TaskWorker(object(), "worker-1", lease_seconds=5)


def test_claim_parses_lease_without_exposing_it_in_task_input():
    client = FakeRpc([STEP])
    worker = TaskWorker(client, "worker-a")
    claimed = worker.claim()
    assert claimed is not None
    assert claimed.step_id == UUID(STEP["step_id"])
    assert claimed.input == {"topic": "testing"}
    assert claimed.lease_token == UUID(STEP["lease_token"])
    assert client.calls[0][0] == "claim_task_step"


def test_run_once_commits_output_using_the_claimed_token():
    client = FakeRpc([STEP, True, True])
    worker = TaskWorker(client, "worker-a")
    result = worker.run_once(lambda step: {"answer": "done"})
    assert result == "completed"
    assert client.calls[1][0] == "renew_task_step_lease"
    assert client.calls[2][0] == "complete_task_step"
    assert client.calls[2][1]["p_lease_token"] == STEP["lease_token"]


def test_run_once_records_handler_failure():
    client = FakeRpc([STEP, True, {"accepted": True, "step_status": "pending"}])
    worker = TaskWorker(client, "worker-a")
    def fail(_step):
        raise RuntimeError("temporary provider timeout")
    assert worker.run_once(fail) == "failed_or_retry_scheduled"
    assert client.calls[2][0] == "fail_task_step"
    assert client.calls[2][1]["p_error_code"] == "tool_execution_failed"
    assert client.calls[2][1]["p_error_message"] == (
        "Step execution failed. Sensitive diagnostic details were not stored."
    )


def test_run_once_reports_stale_lease_without_claiming_success():
    client = FakeRpc([STEP, True, False])
    worker = TaskWorker(client, "worker-a")
    assert worker.run_once(lambda _step: {"ok": True}) == "lease_lost"
    assert client.calls[1][0] == "renew_task_step_lease"
