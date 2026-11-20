from __future__ import annotations

from time import time
from uuid import uuid4

import httpx
import pytest

from app.services.runtime_provisioner_http import HTTPSRuntimeLeaseProvider, RuntimeProvisionerError

ORIGIN = "https://runtime-broker.internal:9443"


def provider(handler):
    return HTTPSRuntimeLeaseProvider(
        base_url=ORIGIN,
        bearer_token="x" * 48,
        allowed_origins=frozenset({ORIGIN}),
        transport=httpx.MockTransport(handler),
    )


def test_acquire_sends_only_task_attempt_identity_and_returns_opaque_lease():
    task, run, runtime = str(uuid4()), str(uuid4()), str(uuid4())
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(201, json={
            "runtime_id": runtime, "task_id": task, "engine_run_id": run,
            "engine_id": "opencode", "base_url": "https://opencode.internal:8443",
            "access_token": "t" * 48, "expires_at": time() + 600,
        })

    client = provider(handler)
    try:
        lease = client.acquire(task, run, "opencode")
    finally:
        client.close()
    assert lease.runtime_id == runtime
    assert seen["path"] == "/v1/runtimes"
    assert '"engine_id":"opencode"' in seen["body"]
    assert "access_token" not in seen["body"]


def test_acquire_rejects_mismatched_attempt_identity():
    client = provider(lambda request: httpx.Response(201, json={}))
    try:
        with pytest.raises(ValueError, match="identity_invalid"):
            client.acquire(str(uuid4()), str(uuid4()), "../opencode")
    finally:
        client.close()


def test_provisioner_redirect_is_rejected():
    client = provider(lambda request: httpx.Response(302, headers={"location": "https://attacker.invalid"}))
    try:
        with pytest.raises(RuntimeProvisionerError, match="unavailable"):
            client.acquire(str(uuid4()), str(uuid4()), "opencode")
    finally:
        client.close()


def test_release_requires_confirmed_boolean():
    runtime = str(uuid4())
    client = provider(lambda request: httpx.Response(200, json={"released": "yes"}))
    from app.services.runtime_broker_contract import RuntimeLease
    lease = RuntimeLease(
        runtime_id=runtime, task_id=str(uuid4()), engine_run_id=str(uuid4()),
        engine_id="opencode", base_url="https://opencode.internal:8443",
        access_token="t" * 48, expires_at=time() + 300,
    )
    try:
        with pytest.raises(RuntimeProvisionerError, match="invalid_release_response"):
            client.release(lease)
    finally:
        client.close()
