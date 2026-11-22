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


def test_pinned_opencode_manifest_declares_its_native_limits_and_capabilities():
    from app.services.engine_catalog import build_engine_registry

    registry = build_engine_registry()
    opencode = registry.get("opencode")

    assert opencode is not None
    assert opencode.enabled is False
    assert opencode.adapter is None
    assert {"code.edit", "code.review", "code.test", "code.repository"} <= opencode.capabilities
    assert opencode.max_timeout_seconds == 1800
    assert opencode.max_input_bytes == 48_000
    assert opencode.max_output_bytes == 16_000


def test_worker_registry_accepts_a_new_reviewed_engine_without_builtin_changes(monkeypatch):
    from types import SimpleNamespace
    import app.worker_runtime as worker_runtime
    from app.services.engine_catalog import EngineManifest

    class BrowserAdapter:
        def execute(self, request):
            return EngineResult("suly-test-browser", {"task_id": request.task_id, "ok": True})

    monkeypatch.setattr(worker_runtime, "get_settings", lambda: SimpleNamespace(
        worker_enabled=True, hermes_agent_enabled=False, opencode_enabled=False,
    ))
    manifest = EngineManifest(
        engine_id="suly-test-browser",
        display_name="Browser Use",
        repository="https://github.com/suly-test-browser/suly-test-browser",
        revision="b" * 40,
        license_id="MIT",
        role="isolated browser automation",
        capabilities=frozenset({"browser.navigate"}),
    )
    registry = worker_runtime.build_engine_registry(
        idempotency_key="suly-browser-extension-test",
        on_run_started=lambda _run_id: True,
        additional_manifests=(manifest,),
        additional_runtime_overrides={"suly-test-browser": (True, BrowserAdapter())},
    )

    result = EngineDispatcher(registry).execute(EngineRequest(
        task_id="task-browser-1", capability="browser.navigate",
        input_payload={"url": "https://example.invalid"}, timeout_seconds=30,
    ))
    assert result.engine_id == "suly-test-browser"
    assert result.output["ok"] is True
