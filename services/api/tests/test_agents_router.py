from app.core.auth import AuthenticatedUser
from app.services.engine_registry import EngineDefinition, EngineRegistry
from app.routers import agents


def test_agent_catalog_exposes_only_capabilities_and_enabled_engine_ids(monkeypatch):
    registry = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes",
            capabilities=frozenset({"agent.general"}),
            enabled=True,
        )
    ])
    monkeypatch.setattr(agents, "build_engine_registry", lambda **_kwargs: registry)
    response = agents.list_agents(AuthenticatedUser(id="user-1", email=None))
    items = {item["agent_id"]: item for item in response["items"]}
    assert items["general-agent"]["enabled"] is True
    assert items["general-agent"]["available"] is True
    assert items["general-agent"]["engines"] == ["hermes-agent"]
    assert items["coding-agent"]["enabled"] is False
    assert items["coding-agent"]["available"] is False
    assert all("api_key" not in str(item).lower() for item in response["items"])
    assert all("prompt" not in item for item in response["items"])


def test_agent_catalog_keeps_every_role_unavailable_without_enabled_engines(monkeypatch):
    registry = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes",
            capabilities=frozenset({"agent.general"}),
            enabled=False,
        )
    ])
    monkeypatch.setattr(agents, "build_engine_registry", lambda **_kwargs: registry)
    response = agents.list_agents(AuthenticatedUser(id="user-1", email=None))
    assert all(item["available"] is False for item in response["items"])
