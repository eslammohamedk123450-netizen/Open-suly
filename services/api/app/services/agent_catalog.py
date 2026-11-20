"""Default SULY agent roles mapped to pinned, disabled specialist engines.

Agent roles are product capabilities, not independent permission principals.
They remain disabled until an isolated engine adapter and approval workflow pass
their respective release gates.
"""
from __future__ import annotations

from app.services.agent_manager import AgentDefinition, AgentManager
from app.services.engine_catalog import build_engine_registry


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
        agent_id="browser-agent",
        display_name="SULY Browser Agent",
        capabilities=frozenset({
            "browser.navigate", "browser.interact", "browser.extract",
        }),
        preferred_engines=("browser-use",),
        enabled=False,
        requires_approval=True,
    ),
)


def build_agent_manager() -> AgentManager:
    """Build the product role map without enabling any role or runtime."""
    return AgentManager(build_engine_registry(), AGENT_DEFINITIONS)
