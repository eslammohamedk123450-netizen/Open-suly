"""Lease-based delivery of completed Hermes delegation plans.

This worker-side outbox never starts specialist runtimes. It creates durable
pending-approval handoffs through SULY and relies on the existing approval RPC
to create child tasks. Retries reuse per-request idempotency keys.
"""
from __future__ import annotations

from typing import Any

from app.services.hermes_delegation_bridge import HermesDelegationBridge


class HermesDelegationOutbox:
    def __init__(
        self, *, client: Any, bridge: HermesDelegationBridge, worker_id: str,
        lease_seconds: int = 60,
    ) -> None:
        if client is None or not callable(getattr(client, "rpc", None)):
            raise TypeError("delegation_outbox_client_required")
        if not isinstance(bridge, HermesDelegationBridge):
            raise TypeError("delegation_outbox_bridge_required")
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id.strip()) > 120:
            raise ValueError("delegation_outbox_worker_id_invalid")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 15 <= lease_seconds <= 300:
            raise ValueError("delegation_outbox_lease_invalid")
        self._client = client
        self._bridge = bridge
        self._worker_id = worker_id.strip()
        self._lease_seconds = lease_seconds

    @staticmethod
    def _one(data: Any) -> dict[str, Any] | None:
        if isinstance(data, list):
            data = data[0] if data else None
        return data if isinstance(data, dict) else None

    def process_once(self) -> str:
        """Claim one plan, deliver it idempotently, and checkpoint its outcome."""
        response = self._client.rpc(
            "claim_hermes_delegation_plan",
            {
                "p_worker_id": self._worker_id,
                "p_lease_seconds": self._lease_seconds,
            },
        ).execute()
        row = self._one(response.data)
        if row is None:
            return "idle"

        plan_id = row.get("plan_id")
        lease_token = row.get("lease_token")
        task_id = row.get("task_id")
        user_id = row.get("user_id")
        parent_run_id = row.get("parent_run_id")
        payload = row.get("payload")
        if not all(isinstance(value, str) and value for value in (
            plan_id, lease_token, task_id, user_id, parent_run_id
        )) or not isinstance(payload, dict):
            self._fail(plan_id, lease_token, "delegation_outbox_claim_invalid")
            return "failed"

        try:
            results = self._bridge.submit(
                payload,
                user_id=user_id,
                parent_task_id=task_id,
                parent_run_id=parent_run_id,
                max_child_tasks=len(payload.get("delegations", [])),
                max_parallel_children=1,
            )
            result_payload = {
                "handoffs": [
                    {
                        "handoff_id": item.handoff_id,
                        "target_engine": item.target_engine,
                        "capability": item.capability,
                        "status": item.status,
                    }
                    for item in results
                ]
            }
            completed = self._client.rpc(
                "complete_hermes_delegation_plan",
                {
                    "p_plan_id": plan_id,
                    "p_lease_token": lease_token,
                    "p_result": result_payload,
                },
            ).execute()
            if completed.data is not True:
                return "lease_lost"
            return "submitted"
        except Exception:
            self._fail(plan_id, lease_token, "delegation_delivery_failed")
            return "retry_scheduled"

    def _fail(self, plan_id: Any, lease_token: Any, error_code: str) -> None:
        if not isinstance(plan_id, str) or not isinstance(lease_token, str):
            return
        self._client.rpc(
            "fail_hermes_delegation_plan",
            {
                "p_plan_id": plan_id,
                "p_lease_token": lease_token,
                "p_error_code": error_code,
            },
        ).execute()



def build_delegation_agent_manager() -> AgentManager:
    """Build a routing-only allow-list; adapters are never executed by this registry."""
    from app.core.config import get_settings
    from app.services.agent_catalog import build_agent_manager
    from app.services.engine_catalog import ENGINE_MANIFESTS
    from app.services.engine_registry import EngineDefinition, EngineRegistry

    settings = get_settings()
    runtime_ready = bool(
        settings.worker_enabled
        and settings.opencode_enabled
        and settings.runtime_provisioner_url
        and settings.runtime_provisioner_token
        and settings.runtime_provisioner_allowed_origins
    )
    definitions = [
        EngineDefinition(
            engine_id=manifest.engine_id,
            display_name=manifest.display_name,
            capabilities=manifest.capabilities,
            enabled=runtime_ready and manifest.engine_id == "opencode",
            requires_approval=True,
            max_input_bytes=manifest.max_input_bytes,
            max_output_bytes=manifest.max_output_bytes,
            max_timeout_seconds=manifest.max_timeout_seconds,
        )
        for manifest in ENGINE_MANIFESTS
    ]
    # This registry only selects a target. The database catalog and approval
    # RPC re-check collaboration eligibility; a separate task runtime adapter
    # is created only after the owner approves the handoff.
    return build_agent_manager(EngineRegistry(definitions))
