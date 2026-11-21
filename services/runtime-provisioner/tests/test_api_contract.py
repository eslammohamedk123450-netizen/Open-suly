from __future__ import annotations

import os
os.environ["SULY_PROVISIONER_TOKEN"] = "t" * 48
os.environ.setdefault("RUNTIME_GATEWAY_ORIGIN", "https://runtime.example.test")
os.environ.setdefault("OPENCODE_RUNTIME_IMAGE", "registry.example/opencode@sha256:" + "a" * 64)
os.environ.setdefault("RUNTIME_DB_PATH", "/tmp/suly-runtime-test.sqlite3")

from fastapi.testclient import TestClient
import app.main as runtime_api
runtime_api.SULY_TOKEN = "t" * 48
app = runtime_api.app

client = TestClient(app)


def test_create_requires_service_auth():
    response = client.post("/v1/runtimes", json={
        "task_id": "00000000-0000-4000-8000-000000000001",
        "engine_run_id": "00000000-0000-4000-8000-000000000002",
    })
    assert response.status_code == 401


def test_create_rejects_noncanonical_identity_before_docker():
    response = client.post("/v1/runtimes", headers={"Authorization": "Bearer " + "t" * 48}, json={
        "task_id": "not-a-uuid", "engine_run_id": "00000000-0000-4000-8000-000000000002",
    })
    assert response.status_code == 422


def test_create_rejects_other_engines():
    response = client.post("/v1/runtimes", headers={"Authorization": "Bearer " + "t" * 48}, json={
        "task_id": "00000000-0000-4000-8000-000000000001",
        "engine_run_id": "00000000-0000-4000-8000-000000000002",
        "engine_id": "shell",
    })
    assert response.status_code == 422


def test_create_requires_hermes_profile_and_rejects_opencode_profile():
    headers = {"Authorization": "Bearer " + "t" * 48}
    hermes_without_profile = client.post("/v1/runtimes", headers=headers, json={
        "task_id": "00000000-0000-4000-8000-000000000001",
        "engine_run_id": "00000000-0000-4000-8000-000000000002",
        "engine_id": "hermes-agent",
    })
    assert hermes_without_profile.status_code == 422
    assert hermes_without_profile.json()["detail"] == "runtime_profile_required"
    opencode_with_profile = client.post("/v1/runtimes", headers=headers, json={
        "task_id": "00000000-0000-4000-8000-000000000001",
        "engine_run_id": "00000000-0000-4000-8000-000000000002",
        "engine_id": "opencode",
        "runtime_profile": "suly-hermes-task-v1",
    })
    assert opencode_with_profile.status_code == 422
    assert opencode_with_profile.json()["detail"] == "runtime_profile_not_applicable"



def test_gateway_route_allowlist_is_task_scoped_and_rejects_arbitrary_routes():
    from app.main import _allowed_opencode_route

    assert _allowed_opencode_route("GET", "/api/info")
    assert _allowed_opencode_route("POST", "/api/session")
    assert _allowed_opencode_route("POST", "/api/session/sesABC123/prompt")
    assert _allowed_opencode_route("GET", "/api/session/sesABC123/permission")
    assert _allowed_opencode_route("POST", "/api/session/sesABC123/permission/perABC123/reply")
    assert _allowed_opencode_route("GET", "/api/event")
    assert not _allowed_opencode_route("POST", "/api/session/sesABC123/shell")
    assert not _allowed_opencode_route("GET", "/etc/passwd")


def test_runtime_manager_factory_is_lazy_and_singleton(monkeypatch):
    import app.main as runtime_api

    created = []

    class FakeManager:
        def __init__(self, *, image, workspace_root, engine_id):
            created.append((image, workspace_root, engine_id, object()))
            self.marker = created[-1][2]

    monkeypatch.setattr(runtime_api, "DockerTaskRuntimeManager", FakeManager)
    monkeypatch.setattr(runtime_api, "IMAGE", "registry.example/opencode@sha256:" + "a" * 64)
    monkeypatch.setattr(runtime_api, "_runtime_managers", {})

    first = runtime_api._get_manager("opencode")
    second = runtime_api._get_manager("opencode")

    assert first is second
    assert len(created) == 1


def test_startup_rejects_runtime_egress_opt_in_before_starting_services(monkeypatch):
    import asyncio
    import pytest
    from app.docker_runtime import RuntimeErrorSafe

    monkeypatch.setenv("RUNTIME_ALLOW_EGRESS", "true")
    with pytest.raises(RuntimeErrorSafe, match="egress_proxy_required"):
        asyncio.run(runtime_api.startup())


def test_runtime_manager_factory_rejects_mutable_image_tag(monkeypatch):
    import app.main as runtime_api

    monkeypatch.setattr(runtime_api, "_runtime_managers", {})
    monkeypatch.setattr(runtime_api, "IMAGE", "registry.example/opencode:latest")

    import pytest
    with pytest.raises(RuntimeError, match="digest-pinned"):
        runtime_api._get_manager("opencode")


def test_gateway_body_limit_is_enforced_during_streaming():
    import asyncio
    import pytest
    from fastapi import HTTPException
    from app.main import _read_bounded_request_body

    class FakeRequest:
        headers = {}
        async def stream(self):
            yield b"a" * 40
            yield b"b" * 40

    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_bounded_request_body(FakeRequest(), limit=64))
    assert error.value.status_code == 413


def test_gateway_rejects_oversized_declared_body_before_reading():
    import asyncio
    import pytest
    from fastapi import HTTPException
    from app.main import _read_bounded_request_body

    class FakeRequest:
        headers = {"content-length": "1000"}
        async def stream(self):
            raise AssertionError("body must not be consumed")
            yield b""

    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_bounded_request_body(FakeRequest(), limit=64))
    assert error.value.status_code == 413


def test_event_gateway_forwards_sse_without_buffering(monkeypatch):
    import asyncio

    class FakeUpstream:
        status_code = 200
        headers = {"content-type": "text/event-stream", "cache-control": "no-cache"}

        async def aiter_bytes(self):
            yield b'data: {"event":"session.execution.started"}\\n\\n'

        async def aclose(self):
            self.closed = True

    upstream = FakeUpstream()

    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False

        def build_request(self, method, route, content, headers):
            return (method, route)

        async def send(self, request, stream=False):
            assert stream is True
            return upstream

        async def aclose(self):
            self.closed = True

    clients = []

    def make_client(**kwargs):
        instance = FakeClient(**kwargs)
        clients.append(instance)
        return instance

    monkeypatch.setattr(runtime_api, "_runtime", lambda runtime_id, token: {"host_port": 4096, "engine_id": "opencode"})
    monkeypatch.setattr(runtime_api.httpx, "AsyncClient", make_client)

    response = client.get(
        "/v1/runtime-gateway/00000000-0000-4000-8000-000000000001/api/event",
        headers={"Authorization": "Bearer runtime-token", "Accept": "text/event-stream"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert "session.execution.started" in response.text
    assert getattr(upstream, "closed", False)
    assert clients and clients[0].closed


def test_runtime_recovery_restores_same_task_credential_for_exact_owner(tmp_path, monkeypatch):
    import hashlib
    import time
    import pytest
    from fastapi import HTTPException
    from uuid import uuid4

    runtime_id, task_id, run_id = map(str, (uuid4(), uuid4(), uuid4()))
    database = tmp_path / "runtime-recovery.sqlite3"
    monkeypatch.setattr(runtime_api, "DATABASE", str(database))
    old_token = "o" * 48
    expected_token = runtime_api._derive_runtime_access_token(runtime_id, task_id, run_id)
    db = runtime_api._db()
    try:
        db.execute(
            "INSERT INTO runtimes (runtime_id,task_id,engine_run_id,engine_id,container_id,host_port,token_hash,expires_at,created_at,baseline_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                runtime_id, task_id, run_id, "opencode", "container-id", 4096,
                hashlib.sha256(expected_token.encode()).hexdigest(),
                time.time() + 600, time.time(), "{}",
            ),
        )
        db.commit()
    finally:
        db.close()

    headers = {"Authorization": "Bearer " + "t" * 48}
    wrong_owner = client.post(
        f"/v1/runtimes/{runtime_id}/recover",
        headers=headers,
        json={"task_id": str(uuid4()), "engine_run_id": run_id},
    )
    assert wrong_owner.status_code == 404

    response = client.post(
        f"/v1/runtimes/{runtime_id}/recover",
        headers=headers,
        json={"task_id": task_id, "engine_run_id": run_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_id"] == runtime_id
    assert payload["task_id"] == task_id
    assert payload["engine_run_id"] == run_id
    assert payload["access_token"] == expected_token
    assert payload["access_token"] != old_token

    new_row = runtime_api._runtime(runtime_id, payload["access_token"])
    assert new_row["token_hash"] == hashlib.sha256(payload["access_token"].encode()).hexdigest()
    with pytest.raises(HTTPException):
        runtime_api._runtime(runtime_id, old_token)


def test_execution_uses_upstream_default_basic_auth_username(monkeypatch):
    import asyncio

    captured = {}

    class FakeStreamResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status_code = 200
            self.headers = {"content-type": "application/json"}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def aiter_bytes(self):
            import json
            yield json.dumps(self.payload).encode("utf-8")

    class FakeClient:
        def __init__(self, *, base_url, auth, **kwargs):
            captured["auth"] = auth
            captured["base_url"] = base_url
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def stream(self, method, path, json):
            captured.setdefault("requests", []).append((method, path, json))
            if path == "/api/session":
                return FakeStreamResponse({"data": {"id": "sesABC123"}})
            return FakeStreamResponse({"data": {"ok": True}})

    monkeypatch.setattr(runtime_api, "_runtime", lambda runtime_id, token: {"host_port": 4096, "engine_id": "opencode"})
    monkeypatch.setattr(runtime_api.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(runtime_api.execute(
        "00000000-0000-4000-8000-000000000001",
        runtime_api.ExecuteRequest(prompt="hello"),
        authorization="Bearer " + "x" * 48,
    ))

    assert captured["auth"][0] == "opencode"
    assert result["session_id"] == "sesABC123"


def test_execute_gateway_rejects_oversized_body_before_json_parse(monkeypatch):
    runtime_id = "00000000-0000-4000-8000-000000000001"
    monkeypatch.setattr(runtime_api, "_runtime", lambda _runtime_id, _token: {"host_port": 4096, "engine_id": "opencode"})
    response = client.post(
        f"/v1/runtime-gateway/{runtime_id}/execute",
        headers={"Authorization": "Bearer " + "x" * 48, "Content-Type": "application/json"},
        content=b"x" * 65537,
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "request_too_large"


def test_execute_request_rejects_unexpected_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        runtime_api.ExecuteRequest.model_validate({"prompt": "safe prompt", "extra": "ignored before"})


def test_create_runtime_rejects_oversized_body_before_docker(monkeypatch):
    import pytest
    from fastapi import HTTPException

    monkeypatch.setattr(
        runtime_api, "_get_manager",
        lambda: pytest.fail("Docker manager must not be reached for oversized body"),
    )
    response = client.post(
        "/v1/runtimes",
        headers={"Authorization": "Bearer " + "t" * 48, "Content-Type": "application/json"},
        content=b"x" * (runtime_api.MAX_RUNTIME_CREATE_BODY_BYTES + 1),
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "request_too_large"


def test_create_runtime_rejects_unknown_request_fields():
    response = client.post(
        "/v1/runtimes",
        headers={"Authorization": "Bearer " + "t" * 48, "Content-Type": "application/json"},
        json={
            "task_id": "00000000-0000-4000-8000-000000000001",
            "engine_run_id": "00000000-0000-4000-8000-000000000002",
            "unexpected": "ignored fields are not accepted",
        },
    )
    assert response.status_code == 422



def test_hermes_gateway_allowlist_only_exposes_runs_and_readonly_catalog():
    from app.main import _allowed_hermes_route

    assert _allowed_hermes_route("POST", "/v1/runs")
    assert _allowed_hermes_route("GET", "/v1/runs/run_abc123")
    assert _allowed_hermes_route("GET", "/v1/runs/run_abc123/events")
    assert _allowed_hermes_route("POST", "/v1/runs/run_abc123/stop")
    assert _allowed_hermes_route("POST", "/v1/runs/run_abc123/steer")
    assert _allowed_hermes_route("POST", "/v1/runs/run_abc123/approval")
    assert _allowed_hermes_route("GET", "/v1/skills")
    assert _allowed_hermes_route("GET", "/v1/toolsets")
    assert not _allowed_hermes_route("GET", "/api/sessions")
    assert not _allowed_hermes_route("POST", "/api/sessions")
    assert not _allowed_hermes_route("POST", "/v1/runs/run_abc123/resolve-unknown")
    assert not _allowed_hermes_route("POST", "/v1/runs/run_abc123/approval/always")
    assert not _allowed_hermes_route("GET", "/v1/runs/run_abc123/../../etc/passwd")


def test_runtime_manager_factory_is_distinct_for_each_engine(monkeypatch):
    import app.main as runtime_api

    created = []
    class FakeManager:
        def __init__(self, *, image, workspace_root, engine_id):
            self.image = image
            self.engine_id = engine_id
            created.append(self)

    monkeypatch.setattr(runtime_api, "DockerTaskRuntimeManager", FakeManager)
    monkeypatch.setattr(runtime_api, "IMAGE", "registry.example/opencode@sha256:" + "a" * 64)
    monkeypatch.setattr(runtime_api, "HERMES_IMAGE", "registry.example/hermes@sha256:" + "b" * 64)
    monkeypatch.setattr(runtime_api, "_runtime_managers", {})

    opencode = runtime_api._get_manager("opencode")
    hermes = runtime_api._get_manager("hermes-agent")
    assert opencode is runtime_api._get_manager("opencode")
    assert hermes is runtime_api._get_manager("hermes-agent")
    assert opencode is not hermes
    assert opencode.image.endswith("a" * 64)
    assert hermes.image.endswith("b" * 64)


def test_hermes_manager_requires_digest_pinned_image(monkeypatch):
    import app.main as runtime_api
    import pytest

    monkeypatch.setattr(runtime_api, "HERMES_IMAGE", "registry.example/hermes:latest")
    monkeypatch.setattr(runtime_api, "_runtime_managers", {})
    with pytest.raises(RuntimeError, match="digest-pinned"):
        runtime_api._get_manager("hermes-agent")


def test_hermes_gateway_rejects_opencode_execute_shortcut(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.main import runtime_gateway

    monkeypatch.setattr(
        runtime_api, "_runtime",
        lambda runtime_id, token: {"host_port": 8642, "engine_id": "hermes-agent"},
    )

    class FakeRequest:
        method = "POST"
        headers = {"content-length": "2"}
        async def stream(self):
            raise AssertionError("Hermes must be rejected before reading the execute body")
            yield b""

    with pytest.raises(HTTPException) as error:
        import asyncio
        asyncio.run(runtime_gateway(
            "00000000-0000-4000-8000-000000000001",
            "execute",
            FakeRequest(),
            authorization="Bearer " + "x" * 48,
        ))
    assert error.value.status_code == 404
    assert error.value.detail == "route_not_allowed"


def test_hermes_execute_endpoint_rejects_non_native_execution_path(monkeypatch):
    import pytest
    from fastapi import HTTPException
    import asyncio

    monkeypatch.setattr(
        runtime_api, "_runtime",
        lambda runtime_id, token: {"host_port": 8642, "engine_id": "hermes-agent"},
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(runtime_api.execute(
            "00000000-0000-4000-8000-000000000001",
            runtime_api.ExecuteRequest(prompt="must use native Runs API"),
            authorization="Bearer " + "x" * 48,
        ))
    assert error.value.status_code == 404
    assert error.value.detail == "route_not_allowed"
