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


def test_execute_invokes_enabled_adapter_and_returns_validated_result():
    registry = EngineRegistry([EngineDefinition(
        engine_id="fake-engine", display_name="Fake Engine",
        capabilities=frozenset({"agent.general"}), enabled=True,
        adapter=FakeAdapter(),
    )])
    result = registry.execute("fake-engine", EngineRequest(
        task_id="task-123", capability="agent.general",
        input_payload={"prompt": "hello"}, timeout_seconds=30,
    ))
    assert result == EngineResult(engine_id="fake-engine", output={"accepted": "task-123"})


def test_execute_refuses_disabled_or_unknown_engine():
    registry = EngineRegistry([EngineDefinition(
        engine_id="fake-engine", display_name="Fake Engine",
        capabilities=frozenset({"agent.general"}), adapter=FakeAdapter(),
    )])
    request = EngineRequest("task-123", "agent.general", {"prompt": "hello"})
    with pytest.raises(RuntimeError, match="engine_disabled"):
        registry.execute("fake-engine", request)
    with pytest.raises(ValueError, match="engine_not_registered"):
        registry.execute("missing-engine", request)


def test_execute_rejects_unsupported_capability_and_oversized_input():
    registry = EngineRegistry([EngineDefinition(
        engine_id="fake-engine", display_name="Fake Engine",
        capabilities=frozenset({"agent.general"}), enabled=True,
        max_input_bytes=10, adapter=FakeAdapter(),
    )])
    with pytest.raises(ValueError, match="engine_capability_not_supported"):
        registry.execute("fake-engine", EngineRequest("task-1", "browser.automation", {}))
    with pytest.raises(ValueError, match="engine_input_too_large"):
        registry.execute("fake-engine", EngineRequest("task-1", "agent.general", {"prompt": "x" * 100}))


def test_execute_rejects_invalid_timeout_and_non_json_payload():
    registry = EngineRegistry([EngineDefinition(
        engine_id="fake-engine", display_name="Fake Engine",
        capabilities=frozenset({"agent.general"}), enabled=True,
        adapter=FakeAdapter(),
    )])
    with pytest.raises(ValueError, match="engine_timeout_out_of_bounds"):
        registry.execute("fake-engine", EngineRequest("task-1", "agent.general", {}, 301))
    with pytest.raises(ValueError, match="engine_input_not_json_serializable"):
        registry.execute("fake-engine", EngineRequest("task-1", "agent.general", {"bad": object()}))


def test_execute_rejects_mismatched_engine_identity_and_oversized_output():
    class WrongEngine:
        def execute(self, _request):
            return EngineResult("other-engine", {"ok": True})
    registry = EngineRegistry([EngineDefinition(
        engine_id="fake-engine", display_name="Fake Engine",
        capabilities=frozenset({"agent.general"}), enabled=True,
        adapter=WrongEngine(),
    )])
    request = EngineRequest("task-1", "agent.general", {})
    with pytest.raises(ValueError, match="engine_identity_mismatch"):
        registry.execute("fake-engine", request)
