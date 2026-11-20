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
