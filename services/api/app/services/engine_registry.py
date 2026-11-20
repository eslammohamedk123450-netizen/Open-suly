"""Metadata registry and capability lookup for SULY engine adapters.

The registry is intentionally separate from ToolRegistry: tools define allowed
operations and approval scopes, while engines are isolated execution backends.
No registered engine is enabled by default and this module performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from app.services.engine_contract import EngineAdapter


_ENGINE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{1,95}$")


@dataclass(frozen=True)
class EngineDefinition:
    engine_id: str
    display_name: str
    capabilities: frozenset[str]
    enabled: bool = False
    requires_approval: bool = True
    max_input_bytes: int = 32_000
    max_output_bytes: int = 64_000
    max_timeout_seconds: int = 300
    adapter: EngineAdapter | None = field(default=None, repr=False, compare=False)


class EngineRegistry:
    """In-memory allow-list of engine metadata and optional adapter instances."""

    def __init__(self, definitions: Iterable[EngineDefinition] = ()) -> None:
        self._engines: dict[str, EngineDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: EngineDefinition) -> None:
        if not isinstance(definition, EngineDefinition):
            raise TypeError("engine_definition_required")
        if not _ENGINE_ID.fullmatch(definition.engine_id):
            raise ValueError("invalid_engine_id")
        if not definition.display_name.strip():
            raise ValueError("engine_display_name_required")
        if not definition.capabilities:
            raise ValueError("engine_capabilities_required")
        if any(not _CAPABILITY.fullmatch(item) for item in definition.capabilities):
            raise ValueError("invalid_engine_capability")
        if (
            definition.max_input_bytes < 1
            or definition.max_output_bytes < 1
            or not 1 <= definition.max_timeout_seconds <= 3600
        ):
            raise ValueError("invalid_engine_limits")
        if definition.engine_id in self._engines:
            raise ValueError(f"duplicate_engine:{definition.engine_id}")
        self._engines[definition.engine_id] = definition

    def get(self, engine_id: str) -> EngineDefinition | None:
        return self._engines.get(engine_id)

    def list(self) -> tuple[EngineDefinition, ...]:
        return tuple(self._engines[key] for key in sorted(self._engines))

    def candidates(self, capability: str) -> tuple[EngineDefinition, ...]:
        """Return enabled engines for a capability; never auto-enable a backend."""
        if not isinstance(capability, str) or not _CAPABILITY.fullmatch(capability):
            raise ValueError("invalid_engine_capability")
        return tuple(
            engine
            for engine in self.list()
            if engine.enabled and capability in engine.capabilities
        )
