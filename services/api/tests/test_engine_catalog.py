import pytest

from app.services.engine_catalog import (
    ENGINE_MANIFESTS,
    build_engine_registry,
    validate_engine_manifests,
)


def test_catalog_registers_pinned_engines_but_keeps_every_runtime_disabled():
    registry = build_engine_registry()

    assert {item.engine_id for item in registry.list()} == {
        "hermes-agent", "opencode", "browser-use",
    }
    assert all(item.enabled is False for item in registry.list())
    assert all(item.requires_approval is True for item in registry.list())
    assert all(item.adapter is None for item in registry.list())
    assert registry.candidates("code.edit") == ()
    assert registry.candidates("browser.navigate") == ()


def test_catalog_records_immutable_upstream_provenance():
    assert len(ENGINE_MANIFESTS) == 3
    assert all(len(item.revision) == 40 for item in ENGINE_MANIFESTS)
    assert all(item.license_id == "MIT" for item in ENGINE_MANIFESTS)
    validate_engine_manifests()


def test_catalog_rejects_mutable_upstream_revision():
    invalid = (
        ENGINE_MANIFESTS[0],
        type(ENGINE_MANIFESTS[1])(
            engine_id="opencode",
            display_name="OpenCode",
            repository="https://github.com/anomalyco/opencode",
            revision="dev",
            license_id="MIT",
            role="coding",
            capabilities=frozenset({"code.edit"}),
        ),
    )
    with pytest.raises(ValueError, match="immutable_commit"):
        validate_engine_manifests(invalid)


def test_catalog_rejects_duplicate_engine_ids():
    with pytest.raises(ValueError, match="duplicate_engine_manifest"):
        validate_engine_manifests((ENGINE_MANIFESTS[0], ENGINE_MANIFESTS[0]))


class StubAdapter:
    def execute(self, request):
        from app.services.engine_contract import EngineResult
        return EngineResult("hermes-agent", {"task": request.task_id})


def test_catalog_allows_only_explicit_valid_runtime_override():
    adapter = StubAdapter()
    registry = build_engine_registry({"hermes-agent": (True, adapter)})

    assert registry.get("hermes-agent").enabled is True
    assert registry.get("hermes-agent").adapter is adapter
    assert registry.get("opencode").enabled is False
    assert registry.get("browser-use").enabled is False
    assert registry.candidates("agent.general")[0].engine_id == "hermes-agent"


@pytest.mark.parametrize("overrides, error", [
    ({"unknown-engine": (True, StubAdapter())}, "unknown_engine_runtime_override"),
    ({"hermes-agent": (True, None)}, "enabled_engine_requires_adapter"),
    ({"hermes-agent": (1, StubAdapter())}, "invalid_engine_runtime_override"),
])
def test_catalog_rejects_unsafe_runtime_overrides(overrides, error):
    with pytest.raises(ValueError, match=error):
        build_engine_registry(overrides)



def test_catalog_accepts_additional_reviewed_engine_without_enabling_it():
    from app.services.engine_catalog import EngineManifest

    extra = EngineManifest(
        engine_id="research-worker",
        display_name="Research Worker",
        repository="https://github.com/example/research-worker",
        revision="a" * 40,
        license_id="Apache-2.0",
        role="isolated research specialist",
        capabilities=frozenset({"research.search", "research.summarize"}),
    )
    registry = build_engine_registry(additional_manifests=(extra,))

    definition = registry.get("research-worker")
    assert definition is not None
    assert definition.enabled is False
    assert definition.adapter is None
    assert registry.candidates("research.search") == ()


def test_catalog_requires_explicit_adapter_to_enable_extension():
    from app.services.engine_catalog import EngineManifest

    extra = EngineManifest(
        engine_id="research-worker",
        display_name="Research Worker",
        repository="https://github.com/example/research-worker",
        revision="a" * 40,
        license_id="Apache-2.0",
        role="isolated research specialist",
        capabilities=frozenset({"research.search"}),
    )
    registry = build_engine_registry(
        {"research-worker": (True, StubAdapter())},
        additional_manifests=(extra,),
    )
    assert registry.get("research-worker").enabled is True


def test_catalog_rejects_unreviewed_or_duplicate_extension_manifests():
    from app.services.engine_catalog import EngineManifest

    invalid = EngineManifest(
        engine_id="research-worker",
        display_name="Research Worker",
        repository="https://github.com/example/research-worker",
        revision="latest",
        license_id="Apache-2.0",
        role="research",
        capabilities=frozenset({"research.search"}),
    )
    with pytest.raises(ValueError, match="immutable_commit"):
        build_engine_registry(additional_manifests=(invalid,))
    with pytest.raises(ValueError, match="duplicate_engine_manifest"):
        build_engine_registry(additional_manifests=(ENGINE_MANIFESTS[0],))
