from __future__ import annotations

from types import SimpleNamespace
from threading import Event
from time import sleep
from uuid import UUID

import pytest

from app.services.task_worker import ClaimedStep, TaskWorker


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
    with pytest.raises(ValueError, match="worker_id must be a string"):
        TaskWorker(object(), None)
    with pytest.raises(ValueError, match="heartbeat interval"):
        TaskWorker(object(), "worker-1", heartbeat_interval_seconds=True)


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
        "Step execution failed. Sensitive diagnostic details were not stored"
    )


def test_run_once_reports_stale_lease_without_claiming_success():
    client = FakeRpc([STEP, True, False])
    worker = TaskWorker(client, "worker-a")
    assert worker.run_once(lambda _step: {"ok": True}) == "lease_lost"
    assert client.calls[1][0] == "renew_task_step_lease"


def test_long_handler_renews_lease_before_checkpoint():
    client = FakeRpc([STEP, True, True, True])
    worker = TaskWorker(client, "worker-heartbeat", heartbeat_interval_seconds=0.01)
    heartbeat_seen = Event()

    original_rpc = client.rpc

    def tracked_rpc(name, args):
        prior_calls = len(client.calls)
        result = original_rpc(name, args)
        if name == "renew_task_step_lease" and prior_calls >= 2:
            heartbeat_seen.set()
        return result

    client.rpc = tracked_rpc

    def long_handler(_step):
        assert heartbeat_seen.wait(1)
        return {"ok": True}

    assert worker.run_once(long_handler) == "completed"
    assert [call[0] for call in client.calls] == [
        "claim_task_step",
        "renew_task_step_lease",
        "renew_task_step_lease",
        "complete_task_step",
    ]


def test_worker_never_checkpoints_after_heartbeat_loses_lease():
    client = FakeRpc([STEP, True, False])
    worker = TaskWorker(client, "worker-lost-lease", heartbeat_interval_seconds=0.01)
    heartbeat_seen = Event()
    original_rpc = client.rpc

    def tracked_rpc(name, args):
        prior_calls = len(client.calls)
        result = original_rpc(name, args)
        if name == "renew_task_step_lease" and prior_calls >= 2:
            heartbeat_seen.set()
        return result

    client.rpc = tracked_rpc

    def long_handler(_step):
        assert heartbeat_seen.wait(1)
        sleep(0.02)
        return {"ok": True}

    assert worker.run_once(long_handler) == "lease_lost"
    assert all(call[0] != "complete_task_step" for call in client.calls)


def test_worker_rejects_heartbeat_interval_longer_than_half_lease():
    with pytest.raises(ValueError, match="heartbeat interval"):
        TaskWorker(object(), "worker-a", lease_seconds=30, heartbeat_interval_seconds=16)


def test_cancel_aware_handler_receives_event_on_heartbeat_lease_loss():
    client = FakeRpc([STEP, True, False])
    worker = TaskWorker(client, "worker-cancel-aware", heartbeat_interval_seconds=0.01)
    heartbeat_seen = Event()
    original_rpc = client.rpc

    def tracked_rpc(name, args):
        prior_calls = len(client.calls)
        result = original_rpc(name, args)
        if name == "renew_task_step_lease" and prior_calls >= 2:
            heartbeat_seen.set()
        return result

    client.rpc = tracked_rpc
    cancel_observed = Event()

    def cancel_aware(_step, cancel_event):
        assert heartbeat_seen.wait(1)
        assert cancel_event.wait(1)
        cancel_observed.set()
        return {"ok": True}

    assert worker.run_once(lambda _step: {"unexpected": True}, cancel_aware_handler=cancel_aware) == "lease_lost"
    assert cancel_observed.is_set()
    assert all(call[0] != "complete_task_step" for call in client.calls)


def test_cancel_aware_handler_still_completes_when_lease_held():
    client = FakeRpc([STEP, True, True])
    worker = TaskWorker(client, "worker-cancel-aware-success")
    seen_event = []

    def handler(_step, cancel_event):
        seen_event.append(cancel_event)
        assert not cancel_event.is_set()
        return {"ok": "bounded"}

    assert worker.run_once(lambda _step: {}, cancel_aware_handler=handler) == "completed"
    assert len(seen_event) == 1
    assert client.calls[-1][0] == "complete_task_step"


@pytest.mark.parametrize("field,value,error", [
    ("attempt_count", True, "worker_claim_invalid_attempt_bounds"),
    ("attempt_count", "1", "worker_claim_invalid_attempt_bounds"),
    ("max_attempts", False, "worker_claim_invalid_attempt_bounds"),
    ("step_key", "bad key", "worker_claim_invalid_step_metadata"),
    ("step_key", "research\u200b", "worker_claim_invalid_step_metadata"),
])
def test_claim_rejects_malformed_scalar_fields(field, value, error):
    payload = dict(STEP)
    payload[field] = value
    worker = TaskWorker(FakeRpc([payload]), "worker-invalid-claim")
    with pytest.raises(ValueError, match=error):
        worker.claim()


def test_claim_rejects_non_json_input_values():
    payload = dict(STEP)
    payload["input"] = {"invalid": float("nan")}
    worker = TaskWorker(FakeRpc([payload]), "worker-invalid-json")
    with pytest.raises(ValueError, match="worker_claim_invalid_input"):
        worker.claim()


def test_claim_rejects_input_over_64_kibibytes():
    payload = dict(STEP)
    payload["input"] = {"payload": "x" * (64 * 1024)}
    worker = TaskWorker(FakeRpc([payload]), "worker-oversized-input")
    with pytest.raises(ValueError, match="worker_claim_input_too_large"):
        worker.claim()


@pytest.mark.parametrize("bad_output", [
    None,
    [],
    {"nan": float("nan")},
    {"not_json": object()},
    {"payload": "x" * (64 * 1024)},
])
def test_complete_rejects_invalid_or_oversized_outputs_without_rpc(bad_output):
    client = FakeRpc([])
    worker = TaskWorker(client, "worker-invalid-output")
    # Construct a typed claim without requiring a network/RPC claim.
    claimed = ClaimedStep(
        step_id=UUID(STEP["step_id"]),
        task_id=UUID(STEP["task_id"]),
        user_id=UUID(STEP["user_id"]),
        step_key=STEP["step_key"],
        title=STEP["title"],
        description=STEP["description"],
        input=STEP["input"],
        attempt_count=STEP["attempt_count"],
        max_attempts=STEP["max_attempts"],
        lease_token=UUID(STEP["lease_token"]),
        lease_expires_at=STEP["lease_expires_at"],
    )
    with pytest.raises(ValueError, match="worker_output"):
        worker.complete(claimed, bad_output)
    assert client.calls == []


@pytest.mark.parametrize("rpc_value", ["true", 1, {"ok": True}, False, None])
def test_lease_renewal_requires_literal_boolean_true(rpc_value):
    client = FakeRpc([STEP, rpc_value])
    worker = TaskWorker(client, "worker-strict-renew")
    claimed = worker.claim()
    assert claimed is not None
    assert worker.renew(claimed) is (rpc_value is True)


@pytest.mark.parametrize("rpc_value", ["true", 1, {"ok": True}, False, None])
def test_completion_requires_literal_boolean_true(rpc_value):
    client = FakeRpc([rpc_value])
    worker = TaskWorker(client, "worker-strict-complete")
    claimed = ClaimedStep(
        step_id=UUID(STEP["step_id"]),
        task_id=UUID(STEP["task_id"]),
        user_id=UUID(STEP["user_id"]),
        step_key=STEP["step_key"],
        title=STEP["title"],
        description=STEP["description"],
        input=STEP["input"],
        attempt_count=STEP["attempt_count"],
        max_attempts=STEP["max_attempts"],
        lease_token=UUID(STEP["lease_token"]),
        lease_expires_at=STEP["lease_expires_at"],
    )
    assert worker.complete(claimed, {"result": "ok"}) is (rpc_value is True)


@pytest.mark.parametrize("bad_output", [
    {"nan": float("nan")},
    {"not_json": object()},
    {"payload": "x" * (64 * 1024)},
])
def test_run_once_rejects_bad_output_and_records_safe_failure(bad_output):
    client = FakeRpc([STEP, True, {"accepted": True}])
    worker = TaskWorker(client, "worker-invalid-handler-output")
    assert worker.run_once(lambda _step: bad_output) == "failed_or_retry_scheduled"
    assert client.calls[-1][0] == "fail_task_step"
    assert client.calls[-1][1]["p_error_message"] == (
        "Step execution failed. Sensitive diagnostic details were not stored"
    )
    assert all(call[0] != "complete_task_step" for call in client.calls)



@pytest.mark.parametrize("rpc_value", [
    None,
    True,
    "accepted",
    {"accepted": "true"},
    {"accepted": False},
])
def test_fail_rejects_unconfirmed_rpc_results(rpc_value):
    client = FakeRpc([rpc_value])
    worker = TaskWorker(client, "worker-strict-fail")
    claimed = ClaimedStep(
        step_id=UUID(STEP["step_id"]),
        task_id=UUID(STEP["task_id"]),
        user_id=UUID(STEP["user_id"]),
        step_key=STEP["step_key"],
        title=STEP["title"],
        description=STEP["description"],
        input=STEP["input"],
        attempt_count=STEP["attempt_count"],
        max_attempts=STEP["max_attempts"],
        lease_token=UUID(STEP["lease_token"]),
        lease_expires_at=STEP["lease_expires_at"],
    )
    assert worker.fail(claimed, "tool_execution_failed", "safe") == {"accepted": False}


def test_run_once_does_not_claim_failure_was_recorded_when_rpc_rejects():
    client = FakeRpc([STEP, True, {"accepted": False}])
    worker = TaskWorker(client, "worker-fail-not-accepted")
    assert worker.run_once(lambda _step: (_ for _ in ()).throw(RuntimeError("failed"))) == (
        "failure_not_recorded"
    )


def test_run_once_reports_failure_write_exception_without_claiming_persistence():
    class RaisingFailRpc(FakeRpc):
        def rpc(self, name, args):
            if name == "fail_task_step":
                raise RuntimeError("database unavailable")
            return super().rpc(name, args)

    client = RaisingFailRpc([STEP, True])
    worker = TaskWorker(client, "worker-fail-rpc-error")
    assert worker.run_once(lambda _step: (_ for _ in ()).throw(RuntimeError("failed"))) == (
        "failure_not_recorded"
    )

def test_worker_bounds_shutdown_when_heartbeat_rpc_stalls():
    heartbeat_started = Event()
    release_heartbeat = Event()

    class BlockingHeartbeatRpc(FakeRpc):
        def __init__(self):
            super().__init__([STEP, True, True])
            self.renew_count = 0

        def rpc(self, name, args):
            if name == "renew_task_step_lease":
                self.renew_count += 1
                if self.renew_count == 2:
                    self.calls.append((name, args))
                    heartbeat_started.set()

                    def execute():
                        release_heartbeat.wait(2)
                        return SimpleNamespace(data=True)

                    return SimpleNamespace(execute=execute)
            return super().rpc(name, args)

    client = BlockingHeartbeatRpc()
    worker = TaskWorker(
        client, "worker-stalled-heartbeat", heartbeat_interval_seconds=0.01
    )

    def handler(_step):
        assert heartbeat_started.wait(1)
        return {"ok": True}

    try:
        assert worker.run_once(handler) == "lease_lost"
        assert all(call[0] != "complete_task_step" for call in client.calls)
    finally:
        release_heartbeat.set()

def test_run_once_treats_initial_lease_renewal_exception_as_lease_loss():
    class RaisingRenewRpc(FakeRpc):
        def rpc(self, name, args):
            if name == "renew_task_step_lease":
                raise RuntimeError("database unavailable")
            return super().rpc(name, args)

    client = RaisingRenewRpc([STEP])
    worker = TaskWorker(client, "worker-initial-renew-error")
    handler_called = Event()

    def handler(_step):
        handler_called.set()
        return {"must_not_run": True}

    assert worker.run_once(handler) == "lease_lost"
    assert not handler_called.is_set()
    assert all(call[0] != "complete_task_step" for call in client.calls)


def test_run_once_reports_unconfirmed_completion_rpc_exception():
    class RaisingCompleteRpc(FakeRpc):
        def rpc(self, name, args):
            if name == "complete_task_step":
                raise RuntimeError("connection lost after request")
            return super().rpc(name, args)

    client = RaisingCompleteRpc([STEP, True])
    worker = TaskWorker(client, "worker-completion-uncertain")
    assert worker.run_once(lambda _step: {"answer": "ready"}) == (
        "completion_unconfirmed"
    )
    assert [call[0] for call in client.calls] == [
        "claim_task_step",
        "renew_task_step_lease",
    ]

