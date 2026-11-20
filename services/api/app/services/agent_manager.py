"""Agent role registry and fail-closed routing for SULY.

هذا الملف يعرّف أدوار الوكلاء وقدراتهم فقط؛ لا يشغّل محركات ولا يمنح صلاحيات.
يختار المدير محركاً مسجلاً ومفعّلاً بالفعل، ولا يفعّل أي محرك تلقائياً.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from app.services.engine_registry import EngineDefinition, EngineRegistry


_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


@dataclass(frozen=True)
class AgentDefinition:
    """وصف ثابت لدور وكيل مستقل عن محرك التنفيذ المستخدم."""

    agent_id: str
    display_name: str
    capabilities: frozenset[str]
    preferred_engines: tuple[str, ...] = ()
    enabled: bool = False
    requires_approval: bool = True


@dataclass(frozen=True)
class AgentRoute:
    """نتيجة اختيار الوكيل والمحركات المؤهلة دون بدء تشغيل فعلي."""

    agent: AgentDefinition
    engines: tuple[EngineDefinition, ...]


class AgentManager:
    """يسجل أدوار الوكلاء ويوجهها فقط إلى محركات مسموح بها."""

    def __init__(
        self,
        engines: EngineRegistry,
        agents: Iterable[AgentDefinition] = (),
    ) -> None:
        self._engines = engines
        self._agents: dict[str, AgentDefinition] = {}
        for agent in agents:
            self.register(agent)

    def register(self, agent: AgentDefinition) -> None:
        if not isinstance(agent, AgentDefinition):
            raise TypeError("agent_definition_required")
        if not isinstance(agent.agent_id, str) or not _AGENT_ID.fullmatch(agent.agent_id):
            raise ValueError("invalid_agent_id")
        if not isinstance(agent.display_name, str) or not agent.display_name.strip():
            raise ValueError("agent_display_name_required")
        if not agent.capabilities:
            raise ValueError("agent_capabilities_required")
        if any(
            not isinstance(capability, str)
            or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,95}", capability)
            for capability in agent.capabilities
        ):
            raise ValueError("invalid_agent_capability")
        if len(set(agent.preferred_engines)) != len(agent.preferred_engines):
            raise ValueError("duplicate_preferred_engine")
        if any(not isinstance(engine_id, str) or not engine_id.strip() for engine_id in agent.preferred_engines):
            raise ValueError("invalid_preferred_engine")
        if agent.agent_id in self._agents:
            raise ValueError("duplicate_agent")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def list(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._agents[key] for key in sorted(self._agents))

    def route(self, agent_id: str, capability: str) -> AgentRoute:
        """يرفض الوكيل/القدرة غير المفعّلين ويعيد المحركات المؤهلة فقط."""
        agent = self.get(agent_id)
        if agent is None:
            raise ValueError("agent_not_registered")
        if not agent.enabled:
            raise RuntimeError("agent_disabled")
        if capability not in agent.capabilities:
            raise ValueError("agent_capability_not_supported")

        eligible = self._engines.candidates(capability)
        by_id = {engine.engine_id: engine for engine in eligible}
        ordered = [
            by_id[engine_id]
            for engine_id in agent.preferred_engines
            if engine_id in by_id
        ]
        preferred_ids = {engine.engine_id for engine in ordered}
        ordered.extend(
            engine for engine in eligible
            if engine.engine_id not in preferred_ids
        )
        if not ordered:
            raise RuntimeError("no_enabled_engine_for_agent_capability")
        return AgentRoute(agent=agent, engines=tuple(ordered))
