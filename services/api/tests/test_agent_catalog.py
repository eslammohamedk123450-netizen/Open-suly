import pytest

from app.services.agent_catalog import AGENT_DEFINITIONS, build_agent_manager


def test_default_agent_roles_are_mapped_to_their_specialist_engines():
    manager = build_agent_manager()

    assert {agent.agent_id for agent in manager.list()} == {
        "general-agent", "coding-agent", "browser-agent",
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
    assert len(AGENT_DEFINITIONS) == 3
