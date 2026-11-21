from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.engine_credit_store import EngineCreditStore

USER_ID = "00000000-0000-0000-0000-000000000011"
TASK_ID = "00000000-0000-0000-0000-000000000022"
RUN_ID = "00000000-0000-0000-0000-000000000033"
RESERVATION_ID = "00000000-0000-0000-0000-000000000044"


class FakeRpc:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.value))


def test_grant_uses_server_rpc_and_returns_available_balance():
    client = FakeRpc(150)
    result = EngineCreditStore(client).grant(
        user_id=USER_ID, amount=150, reason="admin_grant",
        idempotency_key="admin:grant:001",
    )
    assert result == 150
    assert client.calls == [("grant_engine_credits", {
        "p_user_id": USER_ID, "p_amount": 150, "p_reason": "admin_grant",
        "p_idempotency_key": "admin:grant:001",
    })]


def test_reserve_uses_exact_task_run_engine_and_idempotency_scope():
    client = FakeRpc(RESERVATION_ID)
    result = EngineCreditStore(client).reserve(
        user_id=USER_ID, task_id=TASK_ID, engine_run_id=RUN_ID,
        engine_id="opencode", amount=300,
        idempotency_key="engine:run:reserve:001",
    )
    assert result == UUID(RESERVATION_ID)
    assert client.calls == [("reserve_engine_credits", {
        "p_user_id": USER_ID, "p_task_id": TASK_ID, "p_engine_run_id": RUN_ID,
        "p_engine_id": "opencode", "p_amount": 300,
        "p_idempotency_key": "engine:run:reserve:001",
    })]


def test_settle_and_release_use_strict_boolean_rpc_results():
    client = FakeRpc(True)
    store = EngineCreditStore(client)
    assert store.settle(
        user_id=USER_ID, reservation_id=RESERVATION_ID,
        actual_credits=125, idempotency_key="engine:run:settle:001",
    )
    assert store.release(
        user_id=USER_ID, reservation_id=RESERVATION_ID,
        reason="engine_cancelled", idempotency_key="engine:run:release:001",
    )
    assert [call[0] for call in client.calls] == [
        "settle_engine_credits", "release_engine_credits",
    ]


def test_expiry_reconciler_uses_bounded_batch_rpc():
    client = FakeRpc(4)
    assert EngineCreditStore(client).release_expired(10) == 4
    assert client.calls == [(
        "release_expired_engine_credit_reservations", {"p_batch_size": 10},
    )]


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, 1_000_001])
def test_reserve_rejects_invalid_amount_before_rpc(amount):
    client = FakeRpc(RESERVATION_ID)
    with pytest.raises(ValueError, match="engine_credit_amount_invalid"):
        EngineCreditStore(client).reserve(
            user_id=USER_ID, task_id=TASK_ID, engine_run_id=RUN_ID,
            engine_id="opencode", amount=amount,
            idempotency_key="engine:run:reserve:001",
        )
    assert client.calls == []


def test_reserve_rejects_unknown_engine_and_noncanonical_ids():
    client = FakeRpc(RESERVATION_ID)
    store = EngineCreditStore(client)
    with pytest.raises(ValueError, match="engine_credit_engine_invalid"):
        store.reserve(
            user_id=USER_ID, task_id=TASK_ID, engine_run_id=RUN_ID,
            engine_id="browser-use", amount=10,
            idempotency_key="engine:run:reserve:001",
        )
    with pytest.raises(ValueError, match="engine_credit_task_invalid"):
        store.reserve(
            user_id=USER_ID, task_id="not-a-uuid", engine_run_id=RUN_ID,
            engine_id="opencode", amount=10,
            idempotency_key="engine:run:reserve:001",
        )
    assert client.calls == []


def test_settle_rejects_non_boolean_rpc_response():
    with pytest.raises(RuntimeError, match="engine_credit_settle_invalid_response"):
        EngineCreditStore(FakeRpc("true")).settle(
            user_id=USER_ID, reservation_id=RESERVATION_ID,
            actual_credits=10, idempotency_key="engine:run:settle:001",
        )


def test_reserve_rejects_invalid_rpc_uuid():
    with pytest.raises(RuntimeError, match="engine_credit_reserve_invalid_response"):
        EngineCreditStore(FakeRpc("not-a-uuid")).reserve(
            user_id=USER_ID, task_id=TASK_ID, engine_run_id=RUN_ID,
            engine_id="hermes-agent", amount=10,
            idempotency_key="engine:run:reserve:001",
        )


@pytest.mark.parametrize("batch_size", [0, -1, 101, True, 1.5])
def test_expiry_reconciler_rejects_invalid_batch_size(batch_size):
    with pytest.raises(ValueError, match="engine_credit_expiry_batch_invalid"):
        EngineCreditStore(FakeRpc(0)).release_expired(batch_size)


def test_expiry_reconciler_rejects_out_of_range_rpc_result():
    with pytest.raises(RuntimeError, match="engine_credit_expiry_invalid_response"):
        EngineCreditStore(FakeRpc(101)).release_expired(100)
