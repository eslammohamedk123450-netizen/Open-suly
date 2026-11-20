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
