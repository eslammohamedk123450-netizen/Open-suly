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


def test_acquire_rejects_oversized_streamed_response_before_json_parse():
    task, run = str(uuid4()), str(uuid4())
    payload = (
        b'{"runtime_id":"' + str(uuid4()).encode() +
        b'","task_id":"' + task.encode() +
        b'","engine_run_id":"' + run.encode() +
        b'","engine_id":"opencode","base_url":"https://opencode.internal:8443",'
        b'"access_token":"' + (b"t" * 48) +
        b'","expires_at":' + str(time() + 300).encode() +
        b',"padding":"' + (b"x" * 20_000) + b'"}'
    )
    client = provider(lambda request: httpx.Response(
        201, content=payload, headers={"content-type": "application/json"}
    ))
    try:
        with pytest.raises(RuntimeProvisionerError, match="response_too_large"):
            client.acquire(task, run, "opencode")
    finally:
        client.close()


def test_acquire_rejects_invalid_content_length_header():
    client = provider(lambda request: httpx.Response(
        201, content=b"{}", headers={
            "content-type": "application/json", "content-length": "not-a-number"
        }
    ))
    try:
        with pytest.raises(RuntimeProvisionerError, match="invalid_response"):
            client.acquire(str(uuid4()), str(uuid4()), "opencode")
    finally:
        client.close()



def test_acquire_sends_bounded_workspace_snapshot_and_parses_gateway_path():
    task, run, runtime = str(uuid4()), str(uuid4()), str(uuid4())
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(201, json={
            "runtime_id": runtime, "task_id": task, "engine_run_id": run,
            "engine_id": "opencode", "base_url": ORIGIN,
            "gateway_path": f"/v1/runtime-gateway/{runtime}",
            "access_token": "t" * 48, "expires_at": time() + 600,
        })

    client = provider(handler)
    try:
        lease = client.acquire(task, run, "opencode", files=[
            {"path": "src/main.py", "content": "print('ok')"}
        ])
    finally:
        client.close()
    assert lease.gateway_path == f"/v1/runtime-gateway/{runtime}"
    assert '"src/main.py"' in seen["body"]
    assert '"sha256"' in seen["body"]


def test_acquire_rejects_secret_paths_in_workspace_snapshot():
    client = provider(lambda request: httpx.Response(201, json={}))
    try:
        with pytest.raises(ValueError, match="reserved"):
            client.acquire(str(uuid4()), str(uuid4()), "opencode", files=[
                {"path": ".env.production", "content": "secret"}
            ])
    finally:
        client.close()

def test_recover_rotates_a_live_task_runtime_lease():
    task, run, runtime = str(uuid4()), str(uuid4()), str(uuid4())
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={
            "runtime_id": runtime, "task_id": task, "engine_run_id": run,
            "engine_id": "opencode", "base_url": ORIGIN,
            "gateway_path": f"/v1/runtime-gateway/{runtime}",
            "access_token": "r" * 48, "expires_at": time() + 600,
        })

    client = provider(handler)
    try:
        lease = client.recover(runtime, task, run)
    finally:
        client.close()

    assert lease.runtime_id == runtime
    assert lease.access_token == "r" * 48
    assert seen["path"] == f"/v1/runtimes/{runtime}/recover"
    assert '"task_id":"' + task + '"' in seen["body"]
    assert '"engine_run_id":"' + run + '"' in seen["body"]
