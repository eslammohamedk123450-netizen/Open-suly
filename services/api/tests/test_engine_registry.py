from dataclasses import dataclass

import pytest

from app.services.engine_contract import EngineRequest, EngineResult
from app.services.engine_registry import EngineDefinition, EngineRegistry


@dataclass
class FakeAdapter:
    def execute(self, request: EngineRequest) -> EngineResult:
        return EngineResult(engine_id="fake-engine", output={"accepted": request.task_id})


def test_registry_keeps_engines_disabled_by_default():
    registry = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes Agent",
            capabilities=frozenset({"agent.general"}),
            adapter=FakeAdapter(),
        )
    ])

    assert registry.get("hermes-agent").enabled is False
    assert registry.candidates("agent.general") == ()


def test_registry_returns_only_enabled_capability_matches():
    registry = EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes Agent",
            capabilities=frozenset({"agent.general", "agent.tools"}),
            enabled=True,
        ),
        EngineDefinition(
            engine_id="browser-use",
            display_name="Browser Use",
            capabilities=frozenset({"browser.automation"}),
            enabled=True,
        ),
    ])

    assert [item.engine_id for item in registry.candidates("agent.general")] == [
        "hermes-agent"
    ]
    assert registry.candidates("computer.use") == ()


def test_registry_rejects_duplicate_engine_ids():
    definition = EngineDefinition(
        engine_id="hermes-agent",
        display_name="Hermes Agent",
        capabilities=frozenset({"agent.general"}),
    )
    registry = EngineRegistry([definition])

    with pytest.raises(ValueError, match="duplicate_engine"):
        registry.register(definition)


@pytest.mark.parametrize("engine_id", ["", "Hermes", "../hermes", "a"])
def test_registry_rejects_invalid_engine_ids(engine_id):
    with pytest.raises(ValueError, match="invalid_engine_id"):
        EngineRegistry([
            EngineDefinition(
                engine_id=engine_id,
                display_name="Invalid",
                capabilities=frozenset({"agent.general"}),
            )
        ])


def test_registry_rejects_invalid_limits():
    with pytest.raises(ValueError, match="invalid_engine_limits"):
        EngineRegistry([
            EngineDefinition(
                engine_id="test-engine",
                display_name="Test",
                capabilities=frozenset({"agent.general"}),
                max_timeout_seconds=0,
            )
        ])


def test_engine_request_contract_does_not_include_identity_or_grants():
    request = EngineRequest(
        task_id="task-123",
        capability="agent.general",
        input_payload={"prompt": "hello"},
    )

    assert request.task_id == "task-123"
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "approved_scopes")
    assert not hasattr(request, "supabase_client")
