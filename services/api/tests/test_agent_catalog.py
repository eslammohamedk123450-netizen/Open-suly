import pytest

from app.services.agent_catalog import AGENT_DEFINITIONS, build_agent_manager


def test_default_agent_roles_are_mapped_to_their_specialist_engines():
    manager = build_agent_manager()

    assert {agent.agent_id for agent in manager.list()} == {
        "general-agent", "coding-agent", "research-agent", "browser-agent", "workflow-agent",
    }
    assert all(agent.enabled is False for agent in manager.list())
    assert all(agent.requires_approval is True for agent in manager.list())
    assert manager.get("general-agent").preferred_engines == ("hermes-agent",)
    assert manager.get("coding-agent").preferred_engines == ("opencode",)
    assert manager.get("browser-agent").preferred_engines == ("browser-use",)


@pytest.mark.parametrize(
    ("agent_id", "capability"),
    [
        ("general-agent", "agent.general"),
        ("coding-agent", "code.edit"),
        ("browser-agent", "browser.navigate"),
    ],
)
def test_default_agent_roles_fail_closed_until_explicit_activation(agent_id, capability):
    manager = build_agent_manager()
    with pytest.raises(RuntimeError, match="agent_disabled"):
        manager.route(agent_id, capability)


def test_agent_catalog_covers_all_registered_roles():
    assert len(AGENT_DEFINITIONS) == 5


def test_role_activation_does_not_overclaim_unintegrated_hermes_capabilities():
    from app.services.engine_registry import EngineDefinition, EngineRegistry

    engines = EngineRegistry([EngineDefinition(
        engine_id="hermes-agent",
        display_name="Hermes Agent",
        capabilities=frozenset({"agent.general"}),
        enabled=True,
    )])
    manager = build_agent_manager(engines)

    assert manager.get("general-agent").enabled is True
    assert manager.get("research-agent").enabled is False
    assert manager.get("coding-agent").enabled is False
    assert manager.get("browser-agent").enabled is False
    assert manager.get("workflow-agent").enabled is False
