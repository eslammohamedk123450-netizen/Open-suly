"""Capability-first dispatcher for registered, isolated engine adapters.

The dispatcher never enables engines or grants permissions. It intersects the
agent planner's ordered preferences with the live EngineRegistry capability
allow-list, then delegates through the registry's bounded execute contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.engine_contract import EngineRequest, EngineResult
from app.services.engine_registry import EngineRegistry


@dataclass(frozen=True)
class DispatchSelection:
    engine_id: str
    capability: str


class EngineDispatcher:
    """Resolve an engine by capability and planner preference, failing closed."""

    def __init__(self, registry: EngineRegistry) -> None:
        if not callable(getattr(registry, "candidates", None)) or not callable(getattr(registry, "execute", None)):
            raise TypeError("engine_registry_required")
        self._registry = registry

    def select(
        self,
        *,
        capability: str,
        preferred_engine_ids: Sequence[str] = (),
    ) -> DispatchSelection:
        candidates = self._registry.candidates(capability)
        if not candidates:
            raise RuntimeError("no_enabled_engine_for_capability")

        candidate_ids = {item.engine_id for item in candidates}
        ordered: list[str] = []
        for engine_id in preferred_engine_ids:
            if not isinstance(engine_id, str):
                raise ValueError("dispatch_preference_invalid")
            if engine_id in candidate_ids and engine_id not in ordered:
                ordered.append(engine_id)

        if ordered:
            return DispatchSelection(engine_id=ordered[0], capability=capability)
        if len(candidates) != 1:
            raise RuntimeError("engine_dispatch_ambiguous")
        return DispatchSelection(engine_id=candidates[0].engine_id, capability=capability)

    def execute(
        self,
        request: EngineRequest,
        *,
        preferred_engine_ids: Sequence[str] = (),
    ) -> EngineResult:
        if not isinstance(request, EngineRequest):
            raise TypeError("engine_request_required")
        selection = self.select(
            capability=request.capability,
            preferred_engine_ids=preferred_engine_ids,
        )
        result = self._registry.execute(selection.engine_id, request)
        if result.engine_id != selection.engine_id:
            raise RuntimeError("engine_dispatch_result_identity_mismatch")
        return result
