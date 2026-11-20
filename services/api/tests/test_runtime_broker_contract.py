from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.runtime_broker_contract import RuntimeLease, TaskScopedRuntimeBroker


TASK_ID = str(uuid4())
RUN_ID = str(uuid4())
ENGINE_ID = "opencode"
ORIGINS = frozenset({"https://opencode-runtime.internal:8443"})


class FakeProvider:
    def __init__(self, lease: RuntimeLease):
        self.lease = lease
        self.released: list[str] = []

    def acquire(self, task_id: str, engine_run_id: str, engine_id: str) -> RuntimeLease:
        return self.lease

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
        "expires_at": 1_900_000_120.0,
    }
    values.update(overrides)
    return RuntimeLease(**values)


def test_runtime_lease_binds_one_task_attempt_and_allowlisted_host():
    lease = make_lease()
    lease.validate(
        task_id=TASK_ID,
        engine_run_id=RUN_ID,
        engine_id=ENGINE_ID,
        allowed_origins=ORIGINS,
        now=1_900_000_000.0,
    )


@pytest.mark.parametrize("base_url", [
    "https://169.254.169.254",
    "http://localhost:2375",
    "https://untrusted.example",
    "https://opencode-runtime.internal:2375",
    "https://opencode-runtime.internal/path",
    "https://user:pass@opencode-runtime.internal",
])
def test_runtime_lease_rejects_untrusted_or_ambiguous_endpoint(base_url):
    lease = make_lease(base_url=base_url)
    with pytest.raises(ValueError, match="base_url"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_origins=ORIGINS,
            now=1_900_000_000.0,
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
    for expiry in (1_899_999_999.0, 1_900_003_601.0):
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
    provider = FakeProvider(lease)
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    with broker.session(TASK_ID, RUN_ID, ENGINE_ID) as acquired:
        assert acquired is lease
        assert broker.active_count == 1

    assert broker.active_count == 0
    assert provider.released == [lease.runtime_id]


def test_runtime_broker_rejects_reuse_of_runtime_identity():
    lease = make_lease()
    provider = FakeProvider(lease)
    broker = TaskScopedRuntimeBroker(provider, allowed_origins=ORIGINS)

    first = broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)
    with pytest.raises(RuntimeError, match="already_leased"):
        broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)

    assert broker.release(first) is True
    assert broker.active_count == 0


def test_runtime_broker_releases_invalid_provider_lease():
    lease = make_lease(base_url="http://169.254.169.254")
    provider = FakeProvider(lease)
    broker = TaskScopedRuntimeBroker(provider, allowed_hosts=HOSTS)

    with pytest.raises(ValueError, match="base_url"):
        broker.acquire(TASK_ID, RUN_ID, ENGINE_ID)

    assert provider.released == [lease.runtime_id]


def test_runtime_lease_rejects_http_even_when_host_is_allowlisted():
    lease = make_lease(base_url="http://opencode-runtime.internal")
    with pytest.raises(ValueError, match="base_url"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_hosts=HOSTS,
            now=1_900_000_000.0,
        )


def test_runtime_lease_rejects_ip_literal_even_if_allowlisted():
    lease = make_lease(base_url="https://169.254.169.254")
    with pytest.raises(ValueError, match="ip_literal"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_hosts=frozenset({"169.254.169.254"}),
            now=1_900_000_000.0,
        )


def test_runtime_lease_requires_exact_host_not_an_allowlisted_parent_domain():
    lease = make_lease(base_url="https://other.opencode-runtime.internal")
    with pytest.raises(ValueError, match="host_not_allowlisted"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_hosts=frozenset({"opencode-runtime.internal"}),
            now=1_900_000_000.0,
        )


def test_runtime_lease_rejects_oversized_access_token():
    lease = make_lease(access_token="x" * 513)
    with pytest.raises(ValueError, match="credential"):
        lease.validate(
            task_id=TASK_ID,
            engine_run_id=RUN_ID,
            engine_id=ENGINE_ID,
            allowed_hosts=HOSTS,
            now=1_900_000_000.0,
        )


def test_runtime_broker_requires_explicit_host_allowlist():
    with pytest.raises(ValueError, match="allowed_hosts"):
        TaskScopedRuntimeBroker(FakeProvider(make_lease()), allowed_origins=frozenset())



def test_runtime_lease_secret_is_not_exposed_by_repr():
    lease = make_lease()
    assert "x" * 48 not in repr(lease)


def test_runtime_broker_rejects_same_runtime_id_for_another_attempt():
    first_task, first_run = str(uuid4()), str(uuid4())
    second_task, second_run = str(uuid4()), str(uuid4())
    shared_runtime_id = str(uuid4())
    first = make_lease(
        task_id=first_task,
        engine_run_id=first_run,
        runtime_id=shared_runtime_id,
    )
    second = make_lease(
        task_id=second_task,
        engine_run_id=second_run,
        runtime_id=shared_runtime_id,
    )

    class SequenceProvider:
        def __init__(self):
            self.leases = [first, second]
            self.released = []
        def acquire(self, *_args):
            return self.leases.pop(0)
        def release(self, lease):
            self.released.append(lease.runtime_id)
            return True

    provider = SequenceProvider()
    broker = TaskScopedRuntimeBroker(provider, allowed_hosts=HOSTS)
    active = broker.acquire(first_task, first_run, ENGINE_ID)
    assert broker.release(active)
    with pytest.raises(RuntimeError, match="runtime_instance_reuse_rejected"):
        broker.acquire(second_task, second_run, ENGINE_ID)
    assert provider.released == [shared_runtime_id, shared_runtime_id]
