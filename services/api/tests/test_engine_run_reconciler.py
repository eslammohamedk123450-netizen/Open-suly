from __future__ import annotations

from uuid import UUID

import pytest

from app.services.engine_run_reconciler import EngineRunReconciler
from app.services.engine_run_store import EngineStopClaim


class FakeStore:
    def __init__(self, claims):
        self.claims = tuple(claims)
        self.finished = []
        self.claim_args = None
        self.reconciled_batches = []
        self.missing_identity_count = 0

    def count_missing_upstream_identity(self, min_age_seconds):
        assert min_age_seconds == 30
        return self.missing_identity_count

    def reconcile_orphans(self, batch_size):
        self.reconciled_batches.append(batch_size)
        return 0

    def claim_pending_stops(self, batch_size, lease_seconds):
        self.claim_args = (batch_size, lease_seconds)
        return self.claims

    def finish_stop_reconciliation(self, claim, *, stop_confirmed):
        self.finished.append((claim, stop_confirmed))
        return True


def claim(engine_id="hermes-agent", upstream_run_id="run_orphan_123"):
    return EngineStopClaim(
        run_id=UUID("00000000-0000-0000-0000-000000000099"),
        engine_id=engine_id,
        upstream_run_id=upstream_run_id,
        reconcile_token=UUID("00000000-0000-0000-0000-000000000088"),
        attempt_count=1,
    )


def test_reconciler_confirms_supported_engine_stop():
    item = claim()
    store = FakeStore([item])
    observed = []
    reconciler = EngineRunReconciler(
        store,
        stop_handlers={"hermes-agent": lambda run_id: observed.append(run_id) or True},
        batch_size=4,
        lease_seconds=90,
    )
    assert reconciler.run_once() == 1
    assert observed == ["run_orphan_123"]
    assert store.reconciled_batches == [4]
    assert store.claim_args == (4, 90)
    assert store.finished == [(item, True)]


def test_reconciler_releases_unknown_engine_for_retry_without_claiming_success():
    item = claim(engine_id="unknown-engine")
    store = FakeStore([item])
    reconciler = EngineRunReconciler(store, stop_handlers={})
    assert reconciler.run_once() == 0
    assert store.finished == [(item, False)]


def test_reconciler_releases_failed_stop_for_bounded_retry():
    item = claim()
    store = FakeStore([item])
    reconciler = EngineRunReconciler(
        store,
        stop_handlers={"hermes-agent": lambda _run_id: False},
    )
    assert reconciler.run_once() == 0
    assert store.finished == [(item, False)]


def test_reconciler_does_not_expose_handler_exception_details():
    item = claim()
    store = FakeStore([item])

    def fail(_run_id):
        raise RuntimeError("secret prompt and provider token")

    reconciler = EngineRunReconciler(
        store,
        stop_handlers={"hermes-agent": fail},
    )
    assert reconciler.run_once() == 0
    assert store.finished == [(item, False)]


@pytest.mark.parametrize("batch_size,lease_seconds", [
    (0, 60), (101, 60), (True, 60), (10, 14), (10, 901), (10, True),
])
def test_reconciler_rejects_invalid_bounds(batch_size, lease_seconds):
    with pytest.raises(ValueError, match="invalid_engine_stop_claim_bounds"):
        EngineRunReconciler(
            FakeStore([]),
            stop_handlers={},
            batch_size=batch_size,
            lease_seconds=lease_seconds,
        )


def test_reconciler_does_not_count_stop_when_claim_finalization_was_rejected():
    item = claim()
    store = FakeStore([item])
    store.finish_stop_reconciliation = lambda *_args, **_kwargs: False
    reconciler = EngineRunReconciler(
        store,
        stop_handlers={"hermes-agent": lambda _run_id: True},
    )
    assert reconciler.run_once() == 0


def test_reconciler_logs_count_of_runs_missing_upstream_identity(caplog):
    store = FakeStore([])
    store.missing_identity_count = 2
    reconciler = EngineRunReconciler(store, stop_handlers={})
    assert reconciler.run_once() == 0
    assert reconciler.run_once() == 0
    assert "stop_pending without an upstream identity: 2" in caplog.text
    assert len([record for record in caplog.records if "without an upstream identity" in record.message]) == 1



def test_reconciler_uses_task_runtime_claim_handler_when_upstream_run_id_is_missing():
    item = EngineStopClaim(
        run_id=UUID("00000000-0000-0000-0000-000000000099"),
        engine_id="hermes-agent",
        upstream_run_id=None,
        reconcile_token=UUID("00000000-0000-0000-0000-000000000088"),
        attempt_count=1,
        task_id=UUID("00000000-0000-0000-0000-000000000001"),
        runtime_id=UUID("00000000-0000-0000-0000-000000000055"),
    )
    store = FakeStore([item])
    seen = []
    reconciler = EngineRunReconciler(
        store,
        claim_handlers={"hermes-agent": lambda claim: seen.append(claim) or True},
    )
    assert reconciler.run_once() == 1
    assert seen == [item]
    assert store.finished == [(item, True)]


def test_reconciler_prefers_runtime_claim_handler_over_legacy_run_id_handler():
    item = EngineStopClaim(
        run_id=UUID("00000000-0000-0000-0000-000000000099"),
        engine_id="hermes-agent",
        upstream_run_id="run_orphan_123",
        reconcile_token=UUID("00000000-0000-0000-0000-000000000088"),
        attempt_count=1,
        task_id=UUID("00000000-0000-0000-0000-000000000001"),
        runtime_id=UUID("00000000-0000-0000-0000-000000000055"),
    )
    store = FakeStore([item])
    observed = []
    reconciler = EngineRunReconciler(
        store,
        stop_handlers={"hermes-agent": lambda _run_id: (_ for _ in ()).throw(
            AssertionError("Legacy stop handler must not be used when a claim handler exists")
        )},
        claim_handlers={"hermes-agent": lambda claim: observed.append(claim.runtime_id) or True},
    )
    assert reconciler.run_once() == 1
    assert observed == [item.runtime_id]


def test_reconciler_uses_generic_runtime_recovery_for_new_engines():
    item = EngineStopClaim(
        run_id=UUID("00000000-0000-0000-0000-000000000099"),
        engine_id="suly-test-browser",
        upstream_run_id=None,
        reconcile_token=UUID("00000000-0000-0000-0000-000000000088"),
        attempt_count=1,
        task_id=UUID("00000000-0000-0000-0000-000000000001"),
        runtime_id=UUID("00000000-0000-0000-0000-000000000055"),
    )
    store = FakeStore([item])
    recovered, released = [], []

    class RuntimeBroker:
        def recover(self, runtime_id, task_id, engine_run_id, *, engine_id):
            recovered.append((runtime_id, task_id, engine_run_id, engine_id))
            return {"runtime_id": runtime_id, "engine_id": engine_id}

        def release(self, lease):
            released.append(lease)
            return True

    reconciler = EngineRunReconciler(store, runtime_broker=RuntimeBroker())
    assert reconciler.run_once() == 1
    assert recovered == [(
        str(item.runtime_id), str(item.task_id), str(item.run_id), "suly-test-browser",
    )]
    assert released == [{"runtime_id": str(item.runtime_id), "engine_id": "suly-test-browser"}]
    assert store.finished == [(item, True)]
