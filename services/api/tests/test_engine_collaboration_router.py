from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.auth import AuthenticatedUser
from app.routers import engine_collaboration as collaboration


USER_ID = str(uuid4())
TASK_ID = uuid4()
RUN_ID = uuid4()
HANDOFF_ID = uuid4()
CHILD_TASK_ID = str(uuid4())


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.columns = None
        self.filters = {}
        self.limit_value = None
        self.order_by = None

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[key] = list(values)
        return self

    def order(self, key, desc=False):
        self.order_by = (key, desc)
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.client.table_calls.append((self.table_name, self.columns, dict(self.filters)))
        if self.table_name == "tasks":
            rows = [{
                "id": str(TASK_ID), "user_id": USER_ID,
                "status": "running", "project_id": str(uuid4()),
            }] if self.filters.get("user_id") == USER_ID and self.filters.get("id") == str(TASK_ID) else []
        elif self.table_name == "engine_collaboration_handoffs":
            rows = [{
                "id": str(HANDOFF_ID), "parent_task_id": str(TASK_ID),
                "user_id": USER_ID, "status": "pending_approval",
                "target_engine": "opencode", "capability": "code.review",
                "created_at": "2026-11-21T00:00:00Z",
            }] if self.filters.get("user_id") == USER_ID else []
        elif self.table_name == "engine_collaboration_events":
            rows = [{
                "id": str(uuid4()), "handoff_id": str(HANDOFF_ID),
                "user_id": USER_ID, "sequence": 1,
                "event_type": "handoff.created", "status": "pending",
                "metadata": {}, "created_at": "2026-11-21T00:00:00Z",
            }] if self.filters.get("user_id") == USER_ID else []
        else:
            rows = []
        return FakeResponse(rows)


class FakeRpc:
    def __init__(self, client, name, params):
        self.client, self.name, self.params = client, name, params

    def execute(self):
        self.client.rpc_calls.append((self.name, self.params))
        if self.name == "create_engine_collaboration_handoff":
            return FakeResponse(str(HANDOFF_ID))
        if self.name == "approve_engine_collaboration_handoff":
            return FakeResponse({
                "handoff_id": str(HANDOFF_ID),
                "child_task_id": CHILD_TASK_ID,
                "status": "running",
                "target_engine": "opencode",
            })
        return FakeResponse(True)


class FakeClient:
    def __init__(self):
        self.rpc_calls = []
        self.table_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, params):
        return FakeRpc(self, name, params)


def auth_user():
    return AuthenticatedUser(id=USER_ID, email=None)


def request(**overrides):
    values = {
        "target_engine": "opencode",
        "capability": "code.review",
        "prompt": "Review the current project changes.",
        "title": "Code review",
        "idempotency_key": "handoff-request-001",
        "max_child_tasks": 2,
        "max_parallel_children": 1,
        "max_runtime_seconds": 300,
        "max_input_bytes": 64000,
    }
    values.update(overrides)
    return collaboration.CreateEngineHandoffRequest(**values)


def test_create_handoff_uses_parent_run_and_only_prompt_title_payload(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)

    result = collaboration.create_engine_handoff(
        TASK_ID, RUN_ID, request(), auth_user()
    )

    name, params = client.rpc_calls[0]
    assert name == "create_engine_collaboration_handoff"
    assert params["p_parent_task_id"] == str(TASK_ID)
    assert params["p_parent_run_id"] == str(RUN_ID)
    assert params["p_user_id"] == USER_ID
    assert params["p_target_engine"] == "opencode"
    assert params["p_input_payload"] == {
        "prompt": "Review the current project changes.",
        "title": "Code review",
    }
    assert result["handoff"]["id"] == str(HANDOFF_ID)


def test_create_handoff_rejects_blank_prompt_before_rpc(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)
    body = request(prompt="   ")

    with pytest.raises(HTTPException) as error:
        collaboration.create_engine_handoff(TASK_ID, RUN_ID, body, auth_user())

    assert error.value.status_code == 422
    assert client.rpc_calls == []


def test_create_handoff_hides_parent_task_owned_by_another_user(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)

    with pytest.raises(HTTPException) as error:
        collaboration.create_engine_handoff(
            TASK_ID, RUN_ID, request(), AuthenticatedUser(id=str(uuid4()), email=None)
        )

    assert error.value.status_code == 404
    assert client.rpc_calls == []


def test_approve_handoff_enqueues_only_after_owner_scoped_lookup(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)

    result = collaboration.approve_task_collaboration(
        TASK_ID, HANDOFF_ID, auth_user()
    )

    name, params = client.rpc_calls[0]
    assert name == "approve_engine_collaboration_handoff"
    assert params == {"p_handoff_id": str(HANDOFF_ID), "p_user_id": USER_ID}
    assert result["child_task_id"] == CHILD_TASK_ID
    assert result["status"] == "running"


def test_approve_handoff_does_not_call_rpc_for_other_owner(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)
    other = AuthenticatedUser(id=str(uuid4()), email=None)

    with pytest.raises(HTTPException) as error:
        collaboration.approve_task_collaboration(TASK_ID, HANDOFF_ID, other)

    assert error.value.status_code == 404
    assert client.rpc_calls == []


def test_list_handoffs_groups_metadata_events_by_handoff(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(collaboration, "_admin_client", lambda: client)

    result = collaboration.list_task_collaboration(TASK_ID, auth_user())

    assert len(result["items"]) == 1
    assert result["items"][0]["events"][0]["event_type"] == "handoff.created"
    assert all(call[2].get("user_id") == USER_ID for call in client.table_calls)


def test_handoff_request_rejects_unexpected_client_fields():
    with pytest.raises(ValueError):
        request(source_engine="hermes-agent", provider_api_key="should-never-be-accepted")
