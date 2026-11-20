from __future__ import annotations

import os
os.environ.setdefault("SULY_PROVISIONER_TOKEN", "t" * 48)
os.environ.setdefault("RUNTIME_GATEWAY_ORIGIN", "https://runtime.example.test")
os.environ.setdefault("OPENCODE_RUNTIME_IMAGE", "registry.example/opencode@sha256:" + "a" * 64)
os.environ.setdefault("RUNTIME_DB_PATH", "/tmp/suly-runtime-test.sqlite3")

from fastapi.testclient import TestClient
from app.main import app

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



def test_gateway_route_allowlist_is_task_scoped_and_rejects_arbitrary_routes():
    from app.main import _allowed_opencode_route

    assert _allowed_opencode_route("GET", "/api/info")
    assert _allowed_opencode_route("POST", "/api/session")
    assert _allowed_opencode_route("POST", "/api/session/sesABC123/prompt")
    assert _allowed_opencode_route("GET", "/api/session/sesABC123/permission")
    assert _allowed_opencode_route("POST", "/api/session/sesABC123/permission/perABC123/reply")
    assert not _allowed_opencode_route("GET", "/api/event")
    assert not _allowed_opencode_route("POST", "/api/session/sesABC123/shell")
    assert not _allowed_opencode_route("GET", "/etc/passwd")


def test_runtime_manager_factory_is_lazy_and_singleton(monkeypatch):
    import app.main as runtime_api

    created = []

    class FakeManager:
        def __init__(self, *, image, workspace_root):
            created.append((image, workspace_root, object()))
            self.marker = created[-1][2]

    monkeypatch.setattr(runtime_api, "DockerTaskRuntimeManager", FakeManager)
    monkeypatch.setattr(runtime_api, "IMAGE", "registry.example/opencode@sha256:" + "a" * 64)
    monkeypatch.setattr(runtime_api, "_runtime_manager", None)

    first = runtime_api._get_manager()
    second = runtime_api._get_manager()

    assert first is second
    assert len(created) == 1


def test_runtime_manager_factory_rejects_mutable_image_tag(monkeypatch):
    import app.main as runtime_api

    monkeypatch.setattr(runtime_api, "_runtime_manager", None)
    monkeypatch.setattr(runtime_api, "IMAGE", "registry.example/opencode:latest")

    import pytest
    with pytest.raises(RuntimeError, match="digest-pinned"):
        runtime_api._get_manager()


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
