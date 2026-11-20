from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.opencode_session_store import OpenCodeSessionStore


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.filters = []
        self.payload = None

    def insert(self, payload):
        self.payload = payload
        self.rows = [{**payload, "id": str(uuid4()), "created_at": "now", "updated_at": "now", "last_activity_at": "now"}]
        return self

    def select(self, *_args):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class FakeClient:
    def __init__(self, rows=None):
        self.query = FakeQuery(rows)

    def table(self, name):
        assert name == "opencode_sessions"
        return self.query


def test_register_persists_only_valid_session_mapping_and_returns_allowlist():
    user_id, project_id = str(uuid4()), str(uuid4())
    client = FakeClient()
    result = OpenCodeSessionStore(client).register(
        user_id=user_id,
        project_id=project_id,
        upstream_session_id="ses_suly_123456",
        title="  Coding session ",
        workspace_revision="rev-1",
    )
    assert result["upstream_session_id"] == "ses_suly_123456"
    assert result["title"] == "Coding session"
    assert "access_token" not in result
    assert "runtime_url" not in result
    assert client.query.payload["user_id"] == user_id
    assert client.query.payload["project_id"] == project_id


@pytest.mark.parametrize("bad", ["../escape", "", "ses", "ses " + "x" * 200])
def test_register_rejects_invalid_upstream_session_ids(bad):
    with pytest.raises(ValueError, match="upstream_session_id_invalid"):
        OpenCodeSessionStore(FakeClient()).register(
            user_id=str(uuid4()),
            project_id=str(uuid4()),
            upstream_session_id=bad,
            title="valid",
        )


def test_register_requires_task_and_engine_run_as_a_pair():
    with pytest.raises(ValueError, match="task_run_pair_required"):
        OpenCodeSessionStore(FakeClient()).register(
            user_id=str(uuid4()),
            project_id=str(uuid4()),
            upstream_session_id="ses_suly_123456",
            title="valid",
            task_id=str(uuid4()),
        )


def test_list_is_owner_and_project_scoped_and_bounded():
    user_id, project_id = str(uuid4()), str(uuid4())
    row = {
        "id": str(uuid4()), "user_id": user_id, "project_id": project_id,
        "upstream_session_id": "ses_suly_123456", "title": "Session",
        "status": "active", "runtime_token": "must-not-leak",
    }
    client = FakeClient([row])
    result = OpenCodeSessionStore(client).list_project(
        user_id=user_id, project_id=project_id, limit=20
    )
    assert len(result) == 1
    assert "runtime_token" not in result[0]
    assert ("user_id", user_id) in client.query.filters
    assert ("project_id", project_id) in client.query.filters
    with pytest.raises(ValueError, match="limit_invalid"):
        OpenCodeSessionStore(client).list_project(
            user_id=user_id, project_id=project_id, limit=1000
        )
