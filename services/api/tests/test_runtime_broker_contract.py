from __future__ import annotations

from time import time
from time import time
from uuid import uuid4

import pytest

from app.services.runtime_broker_contract import RuntimeLease, TaskScopedRuntimeBroker


TASK_ID = str(uuid4())
RUN_ID = str(uuid4())
ENGINE_ID = "opencode"
ORIGINS = frozenset({"https://opencode-runtime.internal:8443"})


class FakeProvider:
    def __init__(self, leases: list[RuntimeLease]):
        self.leases = list(leases)
        self.released: list[str] = []

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        return self.leases.pop(0)

    def release(self, lease: RuntimeLease) -> bool:
        self.released.append(lease.runtime_id)
        return True


def make_lease(**overrides) -> RuntimeLease:
    values = {
        "runtime_id": str(uuid4()),
        "task_id": TASK_ID,
        "engine_run_id": RUN_ID,
        "engine_id": ENGINE_ID,
        "base_url": "https://opencode-runtime.internal:8443",
        "access_token": "x" * 48,
        "expires_at": time() + 1800,
    }
    values.update(overrides)
    return RuntimeLease(**values)


def test_runtime_lease_binds_one_task_attempt_and_exact_origin():
    lease = make_lease()
    lease.validate(
        task_id=TASK_ID,
        engine_run_id=RUN_ID,
        engine_id=ENGINE_ID,
        allowed_origins=ORIGINS,
        now=time(),
    )


@pytest.mark.parametrize("base_url", [
    "https://169.254.169.254",
    "http://localhost:2375",
    "https://untrusted.example",
    "https://opencode-runtime.internal:2375",
    "https://opencode-runtime.internal:8443/path",
    "https://user:pass@opencode-runtime.internal:8443",
])
def test_runtime_lease_rejects_untrusted_or_ambiguous_endpoint(base_url):
    lease = make_lease(base_url=base_url)
    with pytest.raises(ValueError, match="base_url"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_origins=ORIGINS,
            now=time(),
        )


def test_runtime_lease_rejects_task_attempt_or_engine_mismatch():
    lease = make_lease()
    with pytest.raises(ValueError, match="mismatch"):
        lease.validate(
            task_id=str(uuid4()),
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_origins=ORIGINS,
            now=1_900_000_000.0,
        )


def test_runtime_lease_rejects_expired_or_excessively_long_credential_lease():
    current = time()
    for expiry in (current - 1, current + 3601):
        lease = make_lease(expires_at=expiry)
        with pytest.raises(ValueError, match="expiry"):
            lease.validate(
                task_id=TASK_ID,
                engine_run_id=RUN_ID,
                engine_id=ENGINE_ID,
                allowed_origins=ORIGINS,
                now=1_900_000_000.0,
            )


def test_runtime_broker_acquires_once_and_always_attempts_release():
    lease = make_lease()
    provider = FakeProvider([lease])
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    with broker.session(TASK_ID, RUN_ID, ENGINE_ID) as acquired:
        assert acquired is lease
        assert broker.active_count == 1

    assert broker.active_count == 0
    assert provider.released == [lease.runtime_id]


def test_runtime_broker_rejects_reacquiring_same_attempt():
    lease = make_lease()
    provider = FakeProvider([lease])
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    first = broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)
    with pytest.raises(RuntimeError, match="already_leased"):
        broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)

    assert broker.release(first) is True
    assert broker.active_count == 0


def test_runtime_broker_rejects_reused_runtime_identity_across_attempts():
    first_lease = make_lease()
    second_lease = make_lease(
        task_id=str(uuid4()),
        engine_run_id=str(uuid4()),
        runtime_id=first_lease.runtime_id,
    )
    provider = FakeProvider([first_lease, second_lease])
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    first = broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)
    with pytest.raises(RuntimeError, match="runtime_instance_reuse_rejected"):
        broker.acquire(second_lease.task_id, second_lease.engine_run_id, ENGINE_ID)

    assert broker.release(first) is True
    # The duplicate runtime ID may still belong to the first task; never tear it down twice.
    assert provider.released == [first_lease.runtime_id]


def test_runtime_broker_releases_invalid_provider_lease():
    lease = make_lease(base_url="http://169.254.169.254")
    provider = FakeProvider([lease])
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    with pytest.raises(ValueError, match="base_url"):
        broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)

    assert provider.released == [lease.runtime_id]


def test_runtime_broker_requires_explicit_exact_origin_allowlist():
    with pytest.raises(ValueError, match="allowed_origins"):
        TaskScopedRuntimeBroker(FakeProvider([make_lease()]), allowed_origins=frozenset())



def test_runtime_broker_rejects_forged_lease_object_on_release():
    from dataclasses import replace

    lease = make_lease()
    provider = FakeProvider([lease])
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)
    active = broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)
    forged = replace(active)

    assert forged == active
    assert forged is not active
    assert broker.release(forged) is False
    assert broker.active_count == 1
    assert provider.released == []

    assert broker.release(active) is True
    assert broker.active_count == 0
    assert provider.released == [lease.runtime_id]
