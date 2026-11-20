from __future__ import annotations

import pytest

from app.services.agent_manager import AgentDefinition, AgentManager
from app.services.engine_registry import EngineDefinition, EngineRegistry


class StubEngine:
    def __init__(self, engine_id: str):
        self.engine_id = engine_id

    def execute(self, request):
        raise AssertionError("routing must not execute an engine")


def registry():
    return EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes",
            capabilities=frozenset({"general.execute", "research"}),
            enabled=True,
            adapter=StubEngine("hermes-agent"),
        ),
        EngineDefinition(
            engine_id="opencode",
            display_name="OpenCode",
            capabilities=frozenset({"code.edit"}),
            enabled=True,
            adapter=StubEngine("opencode"),
        ),
        EngineDefinition(
            engine_id="disabled-coder",
            display_name="Disabled coder",
            capabilities=frozenset({"code.edit"}),
            enabled=False,
            adapter=StubEngine("disabled-coder"),
        ),
    ])


def test_agent_manager_routes_to_preferred_enabled_engine_without_execution():
    manager = AgentManager(
        registry(),
        [AgentDefinition(
            agent_id="coding-agent",
            display_name="Coding Agent",
            capabilities=frozenset({"code.edit"}),
            preferred_engines=("disabled-coder", "opencode"),
            enabled=True,
        )],
    )
    route = manager.route("coding-agent", "code.edit")
    assert route.agent.agent_id == "coding-agent"
    assert [engine.engine_id for engine in route.engines] == ["opencode"]


def test_agent_manager_keeps_disabled_agents_off():
    manager = AgentManager(
        registry(),
        [AgentDefinition(
            agent_id="research-agent",
            display_name="Research Agent",
            capabilities=frozenset({"research"}),
        )],
    )
    with pytest.raises(RuntimeError, match="agent_disabled"):
        manager.route("research-agent", "research")


def test_agent_manager_rejects_unregistered_agent_and_capability():
    manager = AgentManager(
        registry(),
        [AgentDefinition(
            agent_id="research-agent",
            display_name="Research Agent",
            capabilities=frozenset({"research"}),
            enabled=True,
        )],
    )
    with pytest.raises(ValueError, match="agent_not_registered"):
        manager.route("unknown-agent", "research")
    with pytest.raises(ValueError, match="agent_capability_not_supported"):
        manager.route("research-agent", "code.edit")


def test_agent_manager_fails_closed_when_no_engine_is_enabled():
    engines = EngineRegistry([
        EngineDefinition(
            engine_id="offline-coder",
            display_name="Offline coder",
            capabilities=frozenset({"code.edit"}),
            enabled=False,
        )
    ])
    manager = AgentManager(
        engines,
        [AgentDefinition(
            agent_id="coding-agent",
            display_name="Coding Agent",
            capabilities=frozenset({"code.edit"}),
            enabled=True,
        )],
    )
    with pytest.raises(RuntimeError, match="no_enabled_engine"):
        manager.route("coding-agent", "code.edit")


def test_agent_manager_rejects_duplicate_agent_and_duplicate_preferences():
    definition = AgentDefinition(
        agent_id="coding-agent",
        display_name="Coding Agent",
        capabilities=frozenset({"code.edit"}),
        enabled=True,
    )
    with pytest.raises(ValueError, match="duplicate_agent"):
        AgentManager(registry(), [definition, definition])
    with pytest.raises(ValueError, match="duplicate_preferred_engine"):
        AgentManager(registry(), [AgentDefinition(
            agent_id="other-agent",
            display_name="Other Agent",
            capabilities=frozenset({"code.edit"}),
            preferred_engines=("opencode", "opencode"),
        )])


def test_agent_manager_rejects_invalid_registry_and_profile_shapes():
    with pytest.raises(TypeError, match="engine_registry_required"):
        AgentManager(object())
    with pytest.raises(ValueError, match="agent_capabilities_required"):
        AgentManager(registry(), [AgentDefinition(
            agent_id="invalid-agent",
            display_name="Invalid",
            capabilities=set({"research"}),
        )])
    with pytest.raises(ValueError, match="preferred_engines_must_be_tuple"):
        AgentManager(registry(), [AgentDefinition(
            agent_id="invalid-agent",
            display_name="Invalid",
            capabilities=frozenset({"research"}),
            preferred_engines=["hermes-agent"],
        )])
    with pytest.raises(ValueError, match="invalid_agent_flags"):
        AgentManager(registry(), [AgentDefinition(
            agent_id="invalid-agent",
            display_name="Invalid",
            capabilities=frozenset({"research"}),
            enabled=1,
        )])
    with pytest.raises(ValueError, match="invalid_preferred_engine"):
        AgentManager(registry(), [AgentDefinition(
            agent_id="invalid-agent",
            display_name="Invalid",
            capabilities=frozenset({"research"}),
            preferred_engines=("unsafe/engine",),
        )])


def test_agent_manager_rejects_non_string_route_values():
    manager = AgentManager(registry())
    with pytest.raises(ValueError, match="invalid_agent_route"):
        manager.route([], "research")
    with pytest.raises(ValueError, match="invalid_agent_route"):
        manager.route("agent", [])
