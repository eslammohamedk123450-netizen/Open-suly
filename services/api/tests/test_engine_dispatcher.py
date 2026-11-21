from __future__ import annotations

import pytest

from app.services.engine_contract import EngineRequest, EngineResult
from app.services.engine_dispatcher import EngineDispatcher
from app.services.engine_registry import EngineDefinition, EngineRegistry


class Adapter:
    def __init__(self, engine_id: str):
        self.engine_id = engine_id
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return EngineResult(self.engine_id, {"task_id": request.task_id})


def test_dispatcher_uses_capability_and_planner_preference():
    hermes = Adapter("hermes-agent")
    opencode = Adapter("opencode")
    registry = EngineRegistry((
        EngineDefinition("hermes-agent", "Hermes", frozenset({"agent.general"}), True, adapter=hermes),
        EngineDefinition("opencode", "OpenCode", frozenset({"agent.general", "code.edit"}), True, adapter=opencode),
    ))
    dispatcher = EngineDispatcher(registry)

    result = dispatcher.execute(
        EngineRequest("task-1", "agent.general", {"prompt": "hello"}),
        preferred_engine_ids=("opencode", "hermes-agent"),
    )

    assert result.engine_id == "opencode"
    assert opencode.calls == 1
    assert hermes.calls == 0


def test_dispatcher_fails_closed_when_multiple_candidates_are_ambiguous():
    registry = EngineRegistry((
        EngineDefinition("hermes-agent", "Hermes", frozenset({"agent.general"}), True, adapter=Adapter("hermes-agent")),
        EngineDefinition("opencode", "OpenCode", frozenset({"agent.general"}), True, adapter=Adapter("opencode")),
    ))

    with pytest.raises(RuntimeError, match="ambiguous"):
        EngineDispatcher(registry).select(capability="agent.general")


def test_dispatcher_never_selects_disabled_or_unsupported_engines():
    registry = EngineRegistry((
        EngineDefinition("hermes-agent", "Hermes", frozenset({"agent.general"}), False, adapter=Adapter("hermes-agent")),
    ))

    with pytest.raises(RuntimeError, match="no_enabled_engine"):
        EngineDispatcher(registry).select(capability="agent.general", preferred_engine_ids=("hermes-agent",))
