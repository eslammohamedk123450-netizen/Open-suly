"""SULY agent roles mapped to pinned specialist engines.

A role is enabled only when its capability has a server-enabled engine adapter.
Persisted task approval remains a separate mandatory execution gate.
"""
from __future__ import annotations

from app.services.agent_manager import AgentDefinition, AgentManager
from app.services.engine_catalog import build_engine_registry
from app.services.engine_registry import EngineRegistry


AGENT_DEFINITIONS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        agent_id="general-agent",
        display_name="SULY General Agent",
        capabilities=frozenset({
            "agent.general", "agent.planning", "agent.skills",
            "agent.memory", "agent.delegation",
        }),
        preferred_engines=("hermes-agent",),
        enabled=False,
        requires_approval=True,
    ),
    AgentDefinition(
        agent_id="coding-agent",
        display_name="SULY Coding Agent",
        capabilities=frozenset({
            "code.edit", "code.review", "code.test", "code.repository",
        }),
        preferred_engines=("opencode",),
        enabled=False,
        requires_approval=True,
    ),
    AgentDefinition(
        agent_id="research-agent",
        display_name="SULY Research Agent",
        capabilities=frozenset({"research", "research.summarize"}),
        preferred_engines=("hermes-agent",),
        enabled=False,
        requires_approval=True,
    ),
    AgentDefinition(
        agent_id="browser-agent",
        display_name="SULY Browser Agent",
        capabilities=frozenset({
            "browser.navigate", "browser.interact", "browser.extract",
        }),
        preferred_engines=("browser-use",),
        enabled=False,
        requires_approval=True,
    ),
    AgentDefinition(
        agent_id="workflow-agent",
        display_name="SULY Workflow Agent",
        capabilities=frozenset({"workflow.execute"}),
        preferred_engines=("n8n", "dify"),
        enabled=False,
        requires_approval=True,
    ),
)


def build_agent_manager(engines: EngineRegistry | None = None) -> AgentManager:
    """Enable a role only when at least one requested capability has an enabled engine."""
    registry = engines if engines is not None else build_engine_registry()
    definitions = []
    for agent in AGENT_DEFINITIONS:
        enabled = any(bool(registry.candidates(capability)) for capability in agent.capabilities)
        definitions.append(AgentDefinition(
            agent_id=agent.agent_id,
            display_name=agent.display_name,
            capabilities=agent.capabilities,
            preferred_engines=agent.preferred_engines,
            enabled=enabled,
            requires_approval=agent.requires_approval,
        ))
    return AgentManager(registry, definitions)
