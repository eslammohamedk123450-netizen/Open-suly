"""Pinned upstream engine inventory exposed as disabled SULY metadata.

This catalogue does not install or launch upstream services. Each runtime must
pass its own sandbox, adapter, dependency, and contract gates before activation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from app.services.engine_contract import EngineAdapter
from app.services.engine_registry import EngineDefinition, EngineRegistry


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class EngineManifest:
    engine_id: str
    display_name: str
    repository: str
    revision: str
    license_id: str
    role: str
    capabilities: frozenset[str]


# Immutable upstream revisions inspected on 2026-11-20.
ENGINE_MANIFESTS: tuple[EngineManifest, ...] = (
    EngineManifest(
        engine_id="hermes-agent",
        display_name="Hermes Agent",
        repository="https://github.com/NousResearch/hermes-agent",
        revision="2de9f51b8008a7d49a49221c184f2f11cbfc4af1",
        license_id="MIT",
        role="primary general-purpose agent runtime",
        # Only the SULY capability currently backed by the native Runs adapter.
        # Upstream Hermes may expose more features, but SULY must not route them
        # until their permission, memory, skill, and tool bridges are integrated.
        capabilities=frozenset({"agent.general"}),
    ),
    EngineManifest(
        engine_id="opencode",
        display_name="OpenCode",
        repository="https://github.com/anomalyco/opencode",
        revision="4cca18d80450a3dd6a9a4142028bde84ccb3116e",
        license_id="MIT",
        role="specialist coding agent runtime",
        capabilities=frozenset({
            "code.edit", "code.review", "code.test", "code.repository",
        }),
    ),
    EngineManifest(
        engine_id="browser-use",
        display_name="Browser Use",
        repository="https://github.com/browser-use/browser-use",
        revision="ccbdb8095fbaf903c748880a600054a34c7b6191",
        license_id="MIT",
        role="isolated browser automation runtime",
        capabilities=frozenset({
            "browser.navigate", "browser.interact", "browser.extract",
        }),
    ),
)


def validate_engine_manifests(
    manifests: tuple[EngineManifest, ...] = ENGINE_MANIFESTS,
) -> None:
    """Fail closed on duplicate IDs, mutable refs, or incomplete provenance."""
    seen: set[str] = set()
    for item in manifests:
        if item.engine_id in seen:
            raise ValueError("duplicate_engine_manifest")
        seen.add(item.engine_id)
        if not isinstance(item.revision, str) or not _COMMIT_SHA.fullmatch(item.revision):
            raise ValueError("engine_revision_must_be_immutable_commit")
        if not isinstance(item.repository, str) or not item.repository.startswith("https://github.com/"):
            raise ValueError("engine_repository_must_be_https_github")
        if not item.license_id or not item.role or not item.capabilities:
            raise ValueError("engine_manifest_metadata_required")


def build_engine_registry(
    runtime_overrides: Mapping[str, tuple[bool, EngineAdapter | None]] | None = None,
    *,
    additional_manifests: tuple[EngineManifest, ...] = (),
) -> EngineRegistry:
    """Register pinned built-ins plus reviewed extensions; nothing is enabled implicitly.

    A new engine must arrive with immutable upstream provenance, a declared
    capability set, and an explicit adapter override. Merely adding metadata
    never provisions a runtime or enables collaboration handoffs.
    """
    if not isinstance(additional_manifests, tuple):
        raise ValueError("additional_engine_manifests_must_be_tuple")
    manifests = ENGINE_MANIFESTS + additional_manifests
    validate_engine_manifests(manifests)
    overrides = dict(runtime_overrides or {})
    known_ids = {item.engine_id for item in manifests}
    if set(overrides) - known_ids:
        raise ValueError("unknown_engine_runtime_override")

    definitions = []
    for item in manifests:
        enabled, adapter = overrides.get(item.engine_id, (False, None))
        if not isinstance(enabled, bool):
            raise ValueError("invalid_engine_runtime_override")
        if adapter is not None and not callable(getattr(adapter, "execute", None)):
            raise ValueError("invalid_engine_runtime_adapter")
        if enabled and adapter is None:
            raise ValueError("enabled_engine_requires_adapter")
        definitions.append(EngineDefinition(
            engine_id=item.engine_id,
            display_name=item.display_name,
            capabilities=item.capabilities,
            enabled=enabled,
            requires_approval=True,
            adapter=adapter,
        ))
    return EngineRegistry(definitions)
