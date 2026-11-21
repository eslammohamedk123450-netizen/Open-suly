from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser, get_current_user
from app.main import app
import app.routers.agent_memories as memories


class Query:
    def __init__(self, client):
        self.client = client
        self.filters = []
        self.operation = "select"
        self.payload = None
        self.limit_value = None

    def select(self, _columns):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = deepcopy(payload)
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = deepcopy(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def execute(self):
        rows = self.client.rows
        if self.operation == "insert":
            if any(row["user_id"] == self.payload["user_id"] and row["memory_key"] == self.payload["memory_key"] for row in rows):
                raise RuntimeError("duplicate key")
            now = datetime.now(timezone.utc).isoformat()
            row = {
                "id": str(uuid4()), "created_at": now, **self.payload,
            }
            rows.append(row)
            return SimpleNamespace(data=[deepcopy(row)])

        selected = [
            row for row in rows
            if all(row.get(key) == value for key, value in self.filters)
        ]
        if self.operation == "select":
            selected = selected[:self.limit_value] if self.limit_value else selected
            return SimpleNamespace(data=deepcopy(selected))
        if self.operation == "update":
            for row in selected:
                row.update(self.payload)
            return SimpleNamespace(data=deepcopy(selected))
        if self.operation == "delete":
            for row in selected:
                rows.remove(row)
            return SimpleNamespace(data=[{"id": row["id"]} for row in selected])
        raise AssertionError(self.operation)


class FakeClient:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == "agent_memories"
        return Query(self)


def setup(monkeypatch):
    client = FakeClient()
    current_user = {"value": AuthenticatedUser(id=str(uuid4()), email=None)}
    monkeypatch.setattr(memories, "get_supabase_admin_client", lambda: client)
    monkeypatch.setattr(memories, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=True))
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]
    return client, current_user, TestClient(app)


def teardown():
    app.dependency_overrides.pop(get_current_user, None)


def test_memory_create_list_update_archive_and_delete_are_owner_scoped(monkeypatch):
    client, current_user, api = setup(monkeypatch)
    try:
        created = api.post("/v1/memories", json={
            "memory_key": "learning-goal",
            "content": "Prefer short lessons with practical exercises.",
            "tags": ["learning", "preferences"],
        })
        assert created.status_code == 201
        memory_id = created.json()["item"]["id"]

        listed = api.get("/v1/memories")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

        other_user = AuthenticatedUser(id=str(uuid4()), email=None)
        current_user["value"] = other_user
        assert api.get("/v1/memories").json()["items"] == []
        assert api.delete(f"/v1/memories/{memory_id}").status_code == 404

        current_user["value"] = AuthenticatedUser(id=client.rows[0]["user_id"], email=None)
        updated = api.patch(f"/v1/memories/{memory_id}", json={"status": "archived"})
        assert updated.status_code == 200
        assert updated.json()["item"]["status"] == "archived"

        deleted = api.delete(f"/v1/memories/{memory_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
        assert client.rows == []
    finally:
        teardown()


def test_memory_rejects_secrets_and_duplicate_keys(monkeypatch):
    _client, _user, api = setup(monkeypatch)
    try:
        secret = api.post("/v1/memories", json={
            "memory_key": "secret-note",
            "content": "API_KEY=" + "a" * 32,
        })
        assert secret.status_code == 422

        payload = {"memory_key": "work-style", "content": "Keep project reports concise."}
        assert api.post("/v1/memories", json=payload).status_code == 201
        assert api.post("/v1/memories", json=payload).status_code == 409
    finally:
        teardown()


def test_memory_feature_is_disabled_until_migration_and_setting_are_ready(monkeypatch):
    monkeypatch.setattr(memories, "get_settings", lambda: SimpleNamespace(agent_memory_enabled=False))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=str(uuid4()), email=None)
    try:
        response = TestClient(app).get("/v1/memories")
        assert response.status_code == 503
    finally:
        teardown()
