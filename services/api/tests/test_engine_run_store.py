from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.engine_run_store import EngineRunStore


RUN_ID = UUID("00000000-0000-0000-0000-000000000099")


class FakeRpc:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.value))


def step():
    return SimpleNamespace(
        step_id=UUID("00000000-0000-0000-0000-000000000001"),
        lease_token=UUID("00000000-0000-0000-0000-000000000004"),
    )


def test_start_engine_run_uses_step_and_opaque_lease_token():
    client = FakeRpc(str(RUN_ID))
    run_id = EngineRunStore(client).start(step(), "hermes-agent")
    assert run_id == RUN_ID
    assert client.calls == [(
        "start_engine_run",
        {
            "p_step_id": str(step().step_id),
            "p_lease_token": str(step().lease_token),
            "p_engine_id": "hermes-agent",
        },
    )]


def test_start_engine_run_rejects_invalid_rpc_response():
    with pytest.raises(RuntimeError, match="engine_run_start_failed"):
        EngineRunStore(FakeRpc(None)).start(step(), "hermes-agent")


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_finish_engine_run_uses_lease_guarded_rpc(status):
    client = FakeRpc(True)
    assert EngineRunStore(client).finish(RUN_ID, step(), status, "safe_code")
    assert client.calls == [(
        "finish_engine_run",
        {
            "p_run_id": str(RUN_ID),
            "p_lease_token": str(step().lease_token),
            "p_status": status,
            "p_error_code": "safe_code",
        },
    )]


def test_finish_engine_run_rejects_non_terminal_status():
    with pytest.raises(ValueError, match="invalid_engine_run_terminal_status"):
        EngineRunStore(FakeRpc(True)).finish(RUN_ID, step(), "running")


def test_finish_engine_run_reports_stale_lease_rejection():
    client = FakeRpc(False)
    assert EngineRunStore(client).finish(RUN_ID, step(), "succeeded") is False



def test_attach_upstream_run_id_uses_active_lease():
    client = FakeRpc(True)
    assert EngineRunStore(client).attach_upstream_run_id(
        RUN_ID, step(), "run_hermes_123",
    )
    assert client.calls == [(
        "attach_engine_upstream_run",
        {
            "p_run_id": str(RUN_ID),
            "p_step_id": str(step().step_id),
            "p_lease_token": str(step().lease_token),
            "p_upstream_run_id": "run_hermes_123",
        },
    )]


def test_attach_upstream_run_id_rejects_invalid_identifier():
    with pytest.raises(ValueError, match="invalid_upstream_run_id"):
        EngineRunStore(FakeRpc(True)).attach_upstream_run_id(RUN_ID, step(), " ")


def test_attach_upstream_run_id_reports_lease_loss():
    assert EngineRunStore(FakeRpc(False)).attach_upstream_run_id(
        RUN_ID, step(), "run_hermes_123",
    ) is False


@pytest.mark.parametrize("batch_size", [0, -1, 501, True, 1.5])
def test_reconcile_orphans_rejects_invalid_batch_size(batch_size):
    with pytest.raises(ValueError, match="invalid_reconciliation_batch_size"):
        EngineRunStore(FakeRpc(0)).reconcile_orphans(batch_size)


@pytest.mark.parametrize("value,expected", [(0, 0), (3, 3), ([4], 4), ({"reconcile_orphan_engine_runs": 2}, 2)])
def test_reconcile_orphans_returns_bounded_reconciled_count(value, expected):
    client = FakeRpc(value)
    assert EngineRunStore(client).reconcile_orphans(10) == expected
    assert client.calls == [(
        "reconcile_orphan_engine_runs",
        {"p_batch_size": 10},
    )]


@pytest.mark.parametrize("value", [-1, 11, True, "2", None])
def test_reconcile_orphans_rejects_invalid_rpc_result(value):
    with pytest.raises(RuntimeError, match="engine_run_reconciliation_invalid_response"):
        EngineRunStore(FakeRpc(value)).reconcile_orphans(10)
