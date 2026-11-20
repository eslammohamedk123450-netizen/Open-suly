"""Server-only persistence for bounded engine attempt lifecycle."""
from __future__ import annotations

from uuid import UUID

from supabase import Client

from app.services.task_worker import ClaimedStep


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
        return bool(response.data)

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
        return bool(response.data)

    def reconcile_orphans(self, batch_size: int = 100) -> int:
        """أغلق سجلات المحركات اليتيمة بدفعة محدودة عبر RPC للخادم فقط.

        لا يوقف هذا الإجراء عملية خارجية؛ إيقاف الـruntime مسؤولية reconciler
        منفصل يستخدم معرف التشغيل الخارجي بعد التحقق من سياسة العزل.
        """
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 500:
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
