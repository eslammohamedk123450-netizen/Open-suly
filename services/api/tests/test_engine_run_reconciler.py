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
