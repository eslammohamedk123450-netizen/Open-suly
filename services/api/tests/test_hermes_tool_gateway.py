from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.hermes_tool_gateway import HermesToolGateway


OWNER = str(uuid4())
TASK = str(uuid4())
STEP = str(uuid4())
LEASE = str(uuid4())
APPROVAL_ID = str(uuid4())


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.filters = {}
        self.inserted = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def is_(self, key, value):
        self.filters[key] = value
        return self

    def gt(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_args):
        return self

    def insert(self, row):
        self.inserted = row
        self.client.inserts.append(row)
        return self

    def execute(self):
        if self.table == "tasks":
            data = [{"id": TASK, "status": "running", "cancel_requested_at": None}]
        elif self.table == "task_steps":
            data = [{"id": STEP}] if self.filters.get("lease_token") == LEASE else []
        elif self.table == "tool_approvals":
            data = [{"id": APPROVAL_ID}] if self.client.approved else []
        elif self.table == "tool_approval_events":
            data = []
        else:
            data = []
        return type("Response", (), {"data": data})()


class Client:
    def __init__(self, approved=True):
        self.approved = approved
        self.inserts = []

    def table(self, name):
        return Query(self, name)


def gateway_call(gateway, **overrides):
    values = dict(
        user_id=OWNER, task_id=TASK, step_id=STEP, lease_token=LEASE,
        tool_id="terminal", request_id="approval_req_123456",
    )
    values.update(overrides)
    return gateway.authorize_upstream_tool_approval(**values)


def test_upstream_terminal_approval_audits_without_executing_tool():
    client = Client()
    gateway = HermesToolGateway(client)

    assert gateway_call(gateway) is True
    assert len(client.inserts) == 1
    audit = client.inserts[0]
    assert audit["event_type"] == "tool_invocation_authorized"
    assert audit["permission_scope"] == "engine:hermes-agent:tool:terminal"
    assert audit["metadata"]["action"] == "upstream_tool_approval_once"
    assert audit["metadata"]["tool_id"] == "terminal"
    assert "request_id" not in audit["metadata"]
    assert "arguments" not in audit["metadata"]


def test_upstream_approval_denied_without_exact_active_user_grant():
    client = Client(approved=False)
    gateway = HermesToolGateway(client)

    with pytest.raises(PermissionError, match="approval_required"):
        gateway_call(gateway)
    assert client.inserts == []


def test_upstream_approval_bridge_rejects_other_tools_and_invalid_request_ids():
    gateway = HermesToolGateway(Client())

    with pytest.raises(PermissionError, match="not_supported"):
        gateway_call(gateway, tool_id="browser")
    with pytest.raises(ValueError, match="request_id_invalid"):
        gateway_call(gateway, request_id="../unsafe")
    with pytest.raises(ValueError, match="request_id_invalid"):
        gateway_call(gateway, request_id="short")
