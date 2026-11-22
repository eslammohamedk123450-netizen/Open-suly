from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.agent_manager import AgentDefinition, AgentManager
from app.services.engine_registry import EngineDefinition, EngineRegistry
from app.services.hermes_delegation_bridge import (
    DelegationPlan, DelegationPlanError, HermesDelegationBridge,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeRpc:
    def __init__(self, client, name, params):
        self.client, self.name, self.params = client, name, params

    def execute(self):
        self.client.calls.append((self.name, self.params))
        return FakeResponse(str(uuid4()))


class FakeClient:
    def __init__(self):
        self.calls = []

    def rpc(self, name, params):
        return FakeRpc(self, name, params)


def manager(*, enabled=True, capability="code.edit"):
    engines = EngineRegistry([EngineDefinition(
        engine_id="opencode", display_name="OpenCode",
        capabilities=frozenset({capability}), enabled=enabled,
        max_input_bytes=16000, max_timeout_seconds=900,
    )])
    return AgentManager(engines, [AgentDefinition(
        agent_id="coding-agent", display_name="Coding specialist",
        capabilities=frozenset({capability}), preferred_engines=("opencode",),
        enabled=True, requires_approval=True,
    )])


def plan(**overrides):
    item = {
        "agent_id": "coding-agent", "capability": "code.edit",
        "prompt": "Implement the requested feature",
        "idempotency_key": "hermes-delegation-0001",
        "max_runtime_seconds": 120,
    }
    item.update(overrides)
    return {"schema_version": 1, "delegations": [item]}


def test_structured_plan_is_strict_and_versioned():
    parsed = DelegationPlan.parse(plan())
    assert len(parsed.delegations) == 1
    with pytest.raises(DelegationPlanError, match="root_invalid"):
        DelegationPlan.parse({**plan(), "unexpected": True})
    with pytest.raises(DelegationPlanError, match="schema_unsupported"):
        DelegationPlan.parse({"schema_version": 2, "delegations": []})
    with pytest.raises(DelegationPlanError, match="item_invalid"):
        DelegationPlan.parse({"schema_version": 1, "delegations": [{**plan()["delegations"][0], "command": "rm -rf /"}]})


def test_malformed_or_duplicate_delegation_is_rejected():
    with pytest.raises(DelegationPlanError):
        DelegationPlan.parse("{not-json")
    with pytest.raises(DelegationPlanError, match="prompt_invalid"):
        DelegationPlan.parse(plan(prompt=" "))
    item = plan()["delegations"][0]
    with pytest.raises(DelegationPlanError, match="duplicate_idempotency"):
        DelegationPlan.parse({"schema_version": 1, "delegations": [item, item]})


def test_bridge_routes_by_capability_and_persists_pending_approval_only():
    client = FakeClient()
    bridge = HermesDelegationBridge(client=client, agent_manager=manager())
    owner, task, run = str(uuid4()), str(uuid4()), str(uuid4())
    result = bridge.submit(plan(), user_id=owner, parent_task_id=task, parent_run_id=run)
    assert len(result) == 1
    assert result[0].target_engine == "opencode"
    assert result[0].status == "pending_approval"
    name, params = client.calls[0]
    assert name == "create_engine_collaboration_handoff"
    assert params["p_user_id"] == owner
    assert params["p_parent_task_id"] == task
    assert params["p_parent_run_id"] == run
    assert params["p_target_engine"] == "opencode"
    assert params["p_capability"] == "code.edit"
    assert params["p_max_runtime_seconds"] == 120


def test_bridge_rejects_identity_mismatch_and_unavailable_capability():
    client = FakeClient()
    bridge = HermesDelegationBridge(client=client, agent_manager=manager())
    with pytest.raises(DelegationPlanError, match="parent_task_identity"):
        bridge.submit(plan(), user_id=str(uuid4()), parent_task_id="not-a-uuid", parent_run_id=str(uuid4()))
    with pytest.raises(DelegationPlanError, match="capability_unavailable"):
        HermesDelegationBridge(
            client=client, agent_manager=manager(enabled=False)
        ).submit(plan(), user_id=str(uuid4()), parent_task_id=str(uuid4()), parent_run_id=str(uuid4()))
    assert client.calls == []


def test_bridge_enforces_delegation_budget_before_writing():
    client = FakeClient()
    bridge = HermesDelegationBridge(client=client, agent_manager=manager())
    payload = {"schema_version": 1, "delegations": [plan()["delegations"][0], {
        **plan()["delegations"][0], "idempotency_key": "hermes-delegation-0002",
    }]}
    with pytest.raises(DelegationPlanError, match="budget_invalid"):
        bridge.submit(payload, user_id=str(uuid4()), parent_task_id=str(uuid4()), parent_run_id=str(uuid4()))
    assert client.calls == []
