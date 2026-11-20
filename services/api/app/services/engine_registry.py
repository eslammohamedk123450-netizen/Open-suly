"""Metadata registry and capability lookup for SULY engine adapters.

The registry is intentionally separate from ToolRegistry: tools define allowed
operations and approval scopes, while engines are isolated execution backends.
No registered engine is enabled by default and this module performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Iterable

from app.services.engine_contract import EngineAdapter, EngineRequest, EngineResult


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
        if not isinstance(definition.engine_id, str) or not _ENGINE_ID.fullmatch(definition.engine_id):
            raise ValueError("invalid_engine_id")
        if not isinstance(definition.display_name, str) or not definition.display_name.strip():
            raise ValueError("engine_display_name_required")
        if not isinstance(definition.capabilities, frozenset) or not definition.capabilities:
            raise ValueError("engine_capabilities_required")
        if not isinstance(definition.enabled, bool) or not isinstance(definition.requires_approval, bool):
            raise ValueError("invalid_engine_flags")
        if definition.adapter is not None and not callable(getattr(definition.adapter, "execute", None)):
            raise ValueError("invalid_engine_adapter")
        if any(not isinstance(item, str) or not _CAPABILITY.fullmatch(item) for item in definition.capabilities):
            raise ValueError("invalid_engine_capability")
        if (
            isinstance(definition.max_input_bytes, bool)
            or not isinstance(definition.max_input_bytes, int)
            or definition.max_input_bytes < 1
            or isinstance(definition.max_output_bytes, bool)
            or not isinstance(definition.max_output_bytes, int)
            or definition.max_output_bytes < 1
            or isinstance(definition.max_timeout_seconds, bool)
            or not isinstance(definition.max_timeout_seconds, int)
            or not 1 <= definition.max_timeout_seconds <= 3600
        ):
            raise ValueError("invalid_engine_limits")
        if definition.engine_id in self._engines:
            raise ValueError(f"duplicate_engine:{definition.engine_id}")
        self._engines[definition.engine_id] = definition

    def get(self, engine_id: str) -> EngineDefinition | None:
        if not isinstance(engine_id, str):
            return None
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

    def execute(self, engine_id: str, request: EngineRequest) -> EngineResult:
        """Invoke an enabled adapter after strict metadata and payload checks.

        SULY authorization and persisted approval must already be checked.
        Identity and approval grants are never derived from engine input.
        """
        definition = self.get(engine_id)
        if definition is None:
            raise ValueError("engine_not_registered")
        if not definition.enabled:
            raise RuntimeError("engine_disabled")
        if definition.adapter is None:
            raise RuntimeError("engine_adapter_unavailable")
        if not isinstance(request, EngineRequest):
            raise TypeError("engine_request_required")
        if not isinstance(request.capability, str) or request.capability not in definition.capabilities:
            raise ValueError("engine_capability_not_supported")
        if not isinstance(request.task_id, str) or not request.task_id.strip() or len(request.task_id) > 128:
            raise ValueError("invalid_engine_task_id")
        if isinstance(request.timeout_seconds, bool) or not isinstance(request.timeout_seconds, int) or not 1 <= request.timeout_seconds <= definition.max_timeout_seconds:
            raise ValueError("engine_timeout_out_of_bounds")
        if not isinstance(request.input_payload, dict):
            raise ValueError("engine_input_must_be_object")
        try:
            encoded = json.dumps(request.input_payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("engine_input_not_json_serializable") from exc
        if len(encoded) > definition.max_input_bytes:
            raise ValueError("engine_input_too_large")
        result = definition.adapter.execute(request)
        if not isinstance(result, EngineResult):
            raise ValueError("invalid_engine_result")
        if result.engine_id != definition.engine_id:
            raise ValueError("engine_identity_mismatch")
        if not isinstance(result.output, dict):
            raise ValueError("engine_output_must_be_object")
        try:
            encoded_output = json.dumps(result.output, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("engine_output_not_json_serializable") from exc
        if len(encoded_output) > definition.max_output_bytes:
            raise ValueError("engine_output_too_large")
        return result
