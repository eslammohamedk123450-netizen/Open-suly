"""SULY-controlled delegation bridge for structured Hermes plans.

Hermes may propose work, but only this bridge can turn a validated proposal
into a durable, owner-scoped collaboration handoff. It never starts a runtime:
the existing approval RPC is the only path that creates an executable child.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from uuid import UUID

from app.services.agent_manager import AgentManager

_SCHEMA_VERSION = 1
_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{1,95}$")
_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_ALLOWED_ROOT = frozenset({"schema_version", "delegations"})
_ALLOWED_ITEM = frozenset({
    "agent_id", "capability", "prompt", "title", "idempotency_key",
    "max_runtime_seconds",
})


class DelegationPlanError(ValueError):
    """A Hermes proposal is malformed, unsafe, or cannot be routed."""


@dataclass(frozen=True)
class DelegationRequest:
    agent_id: str
    capability: str
    prompt: str
    idempotency_key: str
    title: str | None = None
    max_runtime_seconds: int = 300

    def validate(self) -> None:
        if not isinstance(self.agent_id, str) or not _AGENT_ID.fullmatch(self.agent_id):
            raise DelegationPlanError("hermes_delegation_agent_invalid")
        if not isinstance(self.capability, str) or not _CAPABILITY.fullmatch(self.capability):
            raise DelegationPlanError("hermes_delegation_capability_invalid")
        if not isinstance(self.prompt, str) or not self.prompt.strip() or len(self.prompt) > 20_000:
            raise DelegationPlanError("hermes_delegation_prompt_invalid")
        if not isinstance(self.idempotency_key, str) or not _IDEMPOTENCY.fullmatch(self.idempotency_key):
            raise DelegationPlanError("hermes_delegation_idempotency_invalid")
        if self.title is not None and (
            not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 120
        ):
            raise DelegationPlanError("hermes_delegation_title_invalid")
        if (
            isinstance(self.max_runtime_seconds, bool)
            or not isinstance(self.max_runtime_seconds, int)
            or not 1 <= self.max_runtime_seconds <= 1800
        ):
            raise DelegationPlanError("hermes_delegation_runtime_invalid")


@dataclass(frozen=True)
class DelegationPlan:
    delegations: tuple[DelegationRequest, ...]

    @classmethod
    def parse(cls, payload: object, *, max_delegations: int = 8) -> "DelegationPlan":
        if isinstance(payload, str):
            if len(payload.encode("utf-8")) > 64_000:
                raise DelegationPlanError("hermes_delegation_plan_too_large")
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError) as exc:
                raise DelegationPlanError("hermes_delegation_json_invalid") from exc
        if not isinstance(payload, dict) or set(payload) != _ALLOWED_ROOT:
            raise DelegationPlanError("hermes_delegation_root_invalid")
        if payload.get("schema_version") != _SCHEMA_VERSION:
            raise DelegationPlanError("hermes_delegation_schema_unsupported")
        raw = payload.get("delegations")
        if not isinstance(raw, list) or not 1 <= len(raw) <= max_delegations:
            raise DelegationPlanError("hermes_delegation_count_invalid")
        requests: list[DelegationRequest] = []
        keys: set[str] = set()
        for item in raw:
            if not isinstance(item, dict) or set(item) - _ALLOWED_ITEM:
                raise DelegationPlanError("hermes_delegation_item_invalid")
            if not {"agent_id", "capability", "prompt", "idempotency_key"} <= set(item):
                raise DelegationPlanError("hermes_delegation_item_incomplete")
            request = DelegationRequest(**item)
            request.validate()
            if request.idempotency_key in keys:
                raise DelegationPlanError("hermes_delegation_duplicate_idempotency_key")
            keys.add(request.idempotency_key)
            requests.append(request)
        return cls(tuple(requests))


@dataclass(frozen=True)
class DelegationResult:
    handoff_id: str
    target_engine: str
    capability: str
    status: str = "pending_approval"

    def validate(self) -> None:
        try:
            if str(UUID(self.handoff_id)) != self.handoff_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as exc:
            raise DelegationPlanError("hermes_delegation_result_id_invalid") from exc
        if not isinstance(self.target_engine, str) or not _AGENT_ID.fullmatch(self.target_engine):
            raise DelegationPlanError("hermes_delegation_result_engine_invalid")
        if self.status != "pending_approval":
            raise DelegationPlanError("hermes_delegation_result_status_invalid")


class HermesDelegationBridge:
    """Validate, capability-route, and persist pending handoffs through SULY."""

    def __init__(self, *, client: Any, agent_manager: AgentManager) -> None:
        if client is None or not callable(getattr(client, "rpc", None)):
            raise TypeError("delegation_supabase_client_required")
        if not isinstance(agent_manager, AgentManager):
            raise TypeError("delegation_agent_manager_required")
        self._client = client
        self._agents = agent_manager

    def submit(
        self, payload: object, *, user_id: str, parent_task_id: str, parent_run_id: str,
        max_child_tasks: int = 1, max_parallel_children: int = 1,
    ) -> tuple[DelegationResult, ...]:
        for value, field in ((user_id, "user"), (parent_task_id, "parent_task"), (parent_run_id, "parent_run")):
            try:
                if str(UUID(value)) != value:
                    raise ValueError
            except (TypeError, ValueError, AttributeError) as exc:
                raise DelegationPlanError(f"hermes_delegation_{field}_identity_invalid") from exc
        plan = DelegationPlan.parse(payload)
        if (
            isinstance(max_child_tasks, bool) or not isinstance(max_child_tasks, int)
            or not 1 <= max_child_tasks <= 8
            or isinstance(max_parallel_children, bool) or not isinstance(max_parallel_children, int)
            or not 1 <= max_parallel_children <= min(2, max_child_tasks)
            or len(plan.delegations) > max_child_tasks
        ):
            raise DelegationPlanError("hermes_delegation_budget_invalid")

        results: list[DelegationResult] = []
        for request in plan.delegations:
            try:
                route = self._agents.route(request.agent_id, request.capability)
            except (ValueError, RuntimeError) as exc:
                raise DelegationPlanError("hermes_delegation_capability_unavailable") from exc
            # SULY chooses from enabled, registered adapters only. No arbitrary engine IDs.
            selected = route.engines[0]
            payload_json: dict[str, str] = {"prompt": request.prompt.strip()}
            if request.title is not None:
                payload_json["title"] = request.title.strip()
            try:
                response = self._client.rpc(
                    "create_engine_collaboration_handoff",
                    {
                        "p_parent_task_id": parent_task_id,
                        "p_parent_run_id": parent_run_id,
                        "p_user_id": user_id,
                        "p_target_engine": selected.engine_id,
                        "p_capability": request.capability,
                        "p_idempotency_key": request.idempotency_key,
                        "p_input_payload": payload_json,
                        "p_max_child_tasks": max_child_tasks,
                        "p_max_parallel_children": max_parallel_children,
                        "p_max_runtime_seconds": min(
                            request.max_runtime_seconds,
                            selected.max_timeout_seconds,
                        ),
                        "p_max_input_bytes": min(64_000, selected.max_input_bytes),
                    },
                ).execute()
                data = response.data
                handoff_id = data[0] if isinstance(data, list) and data else data
                if isinstance(handoff_id, dict):
                    handoff_id = handoff_id.get("id")
                result = DelegationResult(
                    handoff_id=str(handoff_id),
                    target_engine=selected.engine_id,
                    capability=request.capability,
                )
                result.validate()
                results.append(result)
            except DelegationPlanError:
                raise
            except Exception as exc:
                # Never return partially fabricated success; the durable RPC is authoritative.
                raise RuntimeError("hermes_delegation_persistence_failed") from exc
        return tuple(results)
