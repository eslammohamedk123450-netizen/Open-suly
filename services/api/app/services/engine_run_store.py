"""Server-only persistence for bounded engine attempt lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from supabase import Client

from app.services.task_worker import ClaimedStep


@dataclass(frozen=True)
class EngineStopClaim:
    """حجز محدود لإيقاف تشغيل خارجي فقد مالك المهمة lease الخاص به."""

    run_id: UUID
    engine_id: str
    upstream_run_id: str
    reconcile_token: UUID
    attempt_count: int


class EngineRunStore:
    """Lease-guarded RPC adapter; never stores prompts, outputs, or credentials."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def start(self, step: ClaimedStep, engine_id: str) -> UUID:
        response = self._client.rpc(
            "start_engine_run",
            {
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_engine_id": engine_id,
            },
        ).execute()
        value = response.data
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            value = value.get("start_engine_run")
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("engine_run_start_failed") from exc

    def attach_upstream_run_id(
        self,
        run_id: UUID,
        step: ClaimedStep,
        upstream_run_id: str,
    ) -> bool:
        # نرفض المعرف غير النصي أو الفارغ قبل إرساله إلى قاعدة البيانات.
        if not isinstance(upstream_run_id, str) or not 1 <= len(upstream_run_id.strip()) <= 128:
            raise ValueError("invalid_upstream_run_id")
        # نربط تشغيل Hermes بسجل المحاولة باستخدام lease العامل نفسه.
        response = self._client.rpc(
            "attach_engine_upstream_run",
            {
                "p_run_id": str(run_id),
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_upstream_run_id": upstream_run_id.strip(),
            },
        ).execute()
        # false تعني أن العامل فقد ملكية الخطوة أو أن السجل لم يعد صالحًا.
        if not isinstance(response.data, bool):
            raise RuntimeError("engine_run_attach_invalid_response")
        return response.data

    def append_event(
        self,
        run_id: UUID,
        step: ClaimedStep,
        event: dict[str, str | int | float],
    ) -> bool:
        """Persist allow-listed progress metadata only while the task lease is valid."""
        allowed_events = frozenset({
            "tool.started", "tool.completed", "subagent.start", "subagent.complete",
            "run.queued", "run.completed", "run.failed", "run.cancelled",
            "run.interrupted", "run.stopping", "run.steered",
            "approval.request", "approval.responded",
        })
        if not isinstance(event, dict):
            raise ValueError("invalid_engine_run_event")
        allowed_fields = {
            "event", "seq", "timestamp", "approval_request_id", "approval_choice",
        }
        if set(event) - allowed_fields:
            raise ValueError("invalid_engine_run_event_fields")
        event_name = event.get("event")
        if not isinstance(event_name, str) or event_name not in allowed_events:
            raise ValueError("invalid_engine_run_event_name")
        event_seq = event.get("seq")
        if event_seq is not None and (
            isinstance(event_seq, bool) or not isinstance(event_seq, int) or event_seq < 0
        ):
            raise ValueError("invalid_engine_run_event_sequence")
        event_timestamp = event.get("timestamp")
        if event_timestamp is not None and (
            isinstance(event_timestamp, bool)
            or not isinstance(event_timestamp, (int, float))
            or not 0 <= event_timestamp <= 4_102_444_800
        ):
            raise ValueError("invalid_engine_run_event_timestamp")
        approval_request_id = event.get("approval_request_id")
        if approval_request_id is not None and (
            not isinstance(approval_request_id, str)
            or not 1 <= len(approval_request_id) <= 256
            or not approval_request_id.isascii()
            or any(not (ch.isalnum() or ch in "_-.:@") for ch in approval_request_id)
        ):
            raise ValueError("invalid_engine_run_approval_request_id")
        approval_choice = event.get("approval_choice")
        if event_name == "approval.request":
            if approval_request_id is None or approval_choice is not None:
                raise ValueError("invalid_engine_run_approval_metadata")
        elif event_name == "approval.responded":
            if (
                approval_request_id is None
                or not isinstance(approval_choice, str)
                or approval_choice not in {"once", "deny"}
            ):
                raise ValueError("invalid_engine_run_approval_metadata")
        elif approval_request_id is not None or approval_choice is not None:
            raise ValueError("invalid_engine_run_approval_metadata")

        response = self._client.rpc(
            "append_engine_run_event",
            {
                "p_run_id": str(run_id),
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_event_name": event_name,
                "p_event_seq": event_seq,
                "p_event_timestamp": event_timestamp,
                "p_approval_request_id": approval_request_id,
                "p_approval_choice": approval_choice,
            },
        ).execute()
        if not isinstance(response.data, bool):
            raise RuntimeError("engine_run_event_append_invalid_response")
        return response.data

    def finish(
        self,
        run_id: UUID,
        step: ClaimedStep,
        status: str,
        error_code: str | None = None,
    ) -> bool:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("invalid_engine_run_terminal_status")
        response = self._client.rpc(
            "finish_engine_run",
            {
                "p_run_id": str(run_id),
                "p_lease_token": str(step.lease_token),
                "p_status": status,
                "p_error_code": error_code,
            },
        ).execute()
        if not isinstance(response.data, bool):
            raise RuntimeError("engine_run_finish_invalid_response")
        return response.data

    def reconcile_orphans(self, batch_size: int = 100) -> int:
        """أغلق سجلات المحركات اليتيمة بدفعة محدودة عبر RPC للخادم فقط.

        لا يوقف هذا الإجراء عملية خارجية؛ إيقاف الـruntime مسؤولية reconciler
        منفصل يستخدم معرف التشغيل الخارجي بعد التحقق من سياسة العزل.
        """
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 500:
            raise ValueError("invalid_reconciliation_batch_size")
        response = self._client.rpc(
            "reconcile_orphan_engine_runs",
            {"p_batch_size": batch_size},
        ).execute()
        value = response.data
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            value = value.get("reconcile_orphan_engine_runs")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > batch_size:
            raise RuntimeError("engine_run_reconciliation_invalid_response")
        return value

    def claim_pending_stops(
        self,
        batch_size: int = 10,
        lease_seconds: int = 60,
    ) -> tuple[EngineStopClaim, ...]:
        """احجز تشغيلات خارجية معلقة للإيقاف بمهلة مستقلة عن task lease."""
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 100
            or isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or not 15 <= lease_seconds <= 900
        ):
            raise ValueError("invalid_engine_stop_claim_bounds")
        response = self._client.rpc(
            "claim_engine_runs_for_stop",
            {
                "p_batch_size": batch_size,
                "p_lease_seconds": lease_seconds,
            },
        ).execute()
        rows = response.data or []
        if not isinstance(rows, list) or len(rows) > batch_size:
            raise RuntimeError("engine_stop_claim_invalid_response")
        claims: list[EngineStopClaim] = []
        try:
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("invalid_row")
                engine_id = row.get("engine_id")
                upstream_run_id = row.get("upstream_run_id")
                attempt_count = row.get("reconcile_attempt_count")
                if (
                    not isinstance(engine_id, str)
                    or not 2 <= len(engine_id) <= 63
                    or not isinstance(upstream_run_id, str)
                    or not 1 <= len(upstream_run_id) <= 128
                    or isinstance(attempt_count, bool)
                    or not isinstance(attempt_count, int)
                    or attempt_count < 1
                ):
                    raise ValueError("invalid_claim_fields")
                claims.append(EngineStopClaim(
                    run_id=UUID(str(row["run_id"])),
                    engine_id=engine_id,
                    upstream_run_id=upstream_run_id,
                    reconcile_token=UUID(str(row["reconcile_token"])),
                    attempt_count=attempt_count,
                ))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("engine_stop_claim_invalid_response") from exc
        return tuple(claims)

    def finish_stop_reconciliation(
        self,
        claim: EngineStopClaim,
        *,
        stop_confirmed: bool,
    ) -> bool:
        """أغلق السجل بعد تأكيد الحالة النهائية أو حرر الحجز لإعادة المحاولة."""
        if not isinstance(claim, EngineStopClaim) or not isinstance(stop_confirmed, bool):
            raise ValueError("invalid_engine_stop_reconciliation_input")
        response = self._client.rpc(
            "finish_engine_run_reconciliation",
            {
                "p_run_id": str(claim.run_id),
                "p_reconcile_token": str(claim.reconcile_token),
                "p_stop_confirmed": stop_confirmed,
            },
        ).execute()
        if not isinstance(response.data, bool):
            raise RuntimeError("engine_stop_reconciliation_invalid_response")
        return response.data

    def count_missing_upstream_identity(self, min_age_seconds: int = 30) -> int:
        """Count stale stop_pending rows with no upstream ID for operational alerting."""
        if (
            isinstance(min_age_seconds, bool)
            or not isinstance(min_age_seconds, int)
            or not 1 <= min_age_seconds <= 3600
        ):
            raise ValueError("invalid_missing_identity_age")
        response = self._client.rpc(
            "count_engine_runs_missing_upstream_identity",
            {"p_min_age_seconds": min_age_seconds},
        ).execute()
        value = response.data
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            value = value.get("count_engine_runs_missing_upstream_identity")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError("missing_identity_count_invalid_response")
        return value
