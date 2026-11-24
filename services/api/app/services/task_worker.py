"""Trusted worker-side RPC adapter for durable SULY task steps.

This module deliberately does not start a daemon or deploy a worker. It is the
small execution boundary a separately hosted worker process can call.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable
from uuid import UUID

from supabase import Client


_STEP_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_MAX_CLAIM_INPUT_BYTES = 64 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class ClaimedStep:
    step_id: UUID
    task_id: UUID
    user_id: UUID
    step_key: str
    title: str
    description: str
    input: dict[str, Any]
    attempt_count: int
    max_attempts: int
    lease_token: UUID
    lease_expires_at: str


class TaskWorker:
    """Executes one claimed step through server-only, token-guarded RPCs."""

    def __init__(
        self,
        client: Client,
        worker_id: str,
        lease_seconds: int = 90,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        if not isinstance(worker_id, str):
            raise ValueError("worker_id must be a string")
        normalized = worker_id.strip()
        if not normalized or len(normalized) > 120:
            raise ValueError("worker_id must contain 1–120 non-whitespace characters")
        if not 15 <= lease_seconds <= 900:
            raise ValueError("lease_seconds must be between 15 and 900")
        self._client = client
        self.worker_id = normalized
        self.lease_seconds = lease_seconds
        interval = heartbeat_interval_seconds if heartbeat_interval_seconds is not None else max(1.0, lease_seconds / 3)
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not 0.01 <= interval <= lease_seconds / 2
        ):
            raise ValueError("heartbeat interval must be positive and no more than half the lease")
        self.heartbeat_interval_seconds = interval

    def claim(self) -> ClaimedStep | None:
        response = self._client.rpc(
            "claim_task_step",
            {"p_worker_id": self.worker_id, "p_lease_seconds": self.lease_seconds},
        ).execute()
        data = response.data
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return None
        if not isinstance(data, dict):
            raise ValueError("worker_claim_invalid_payload")
        raw_input = data.get("input")
        if not isinstance(raw_input, dict):
            raise ValueError("worker_claim_invalid_input")
        # نرفض الأعداد المنطقية والتحويلات النصية بدل قبولها كعداد محاولات.
        attempt_count = data.get("attempt_count")
        max_attempts = data.get("max_attempts")
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= attempt_count <= max_attempts <= 10
        ):
            raise ValueError("worker_claim_invalid_attempt_bounds")
        step_key = data.get("step_key")
        title = data.get("title")
        description = data.get("description", "")
        lease_expires_at = data.get("lease_expires_at")
        if (
            not isinstance(step_key, str)
            or not _STEP_KEY.fullmatch(step_key)
            or not isinstance(title, str)
            or not title.strip()
            or len(title) > 200
            or not isinstance(description, str)
            or len(description) > 4000
            or not isinstance(lease_expires_at, str)
            or not 1 <= len(lease_expires_at) <= 100
        ):
            raise ValueError("worker_claim_invalid_step_metadata")
        # نتحقق أن المدخل JSON محدود الحجم وقابل للتسلسل قبل تسليمه لأي engine.
        try:
            input_bytes = json.dumps(
                raw_input, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("worker_claim_invalid_input") from exc
        if len(input_bytes) > _MAX_CLAIM_INPUT_BYTES:
            raise ValueError("worker_claim_input_too_large")
        return ClaimedStep(
            step_id=UUID(str(data["step_id"])),
            task_id=UUID(str(data["task_id"])),
            user_id=UUID(str(data["user_id"])),
            step_key=step_key,
            title=title,
            description=description,
            input=raw_input,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            lease_token=UUID(str(data["lease_token"])),
            lease_expires_at=lease_expires_at,
        )

    def renew(self, step: ClaimedStep) -> bool:
        response = self._client.rpc(
            "renew_task_step_lease",
            {
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_lease_seconds": self.lease_seconds,
            },
        ).execute()
        return response.data is True

    def complete(self, step: ClaimedStep, output: dict[str, Any]) -> bool:
        if not isinstance(output, dict):
            raise ValueError("worker_output_invalid")
        try:
            output_bytes = json.dumps(
                output, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("worker_output_invalid") from exc
        if len(output_bytes) > _MAX_OUTPUT_BYTES:
            raise ValueError("worker_output_too_large")
        response = self._client.rpc(
            "complete_task_step",
            {
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_output": output,
            },
        ).execute()
        return response.data is True

    def fail(self, step: ClaimedStep, error_code: str, error_message: str) -> dict[str, Any]:
        response = self._client.rpc(
            "fail_task_step",
            {
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_error_code": error_code[:80],
                "p_error_message": error_message[:2000],
            },
        ).execute()
        data = response.data
        if not isinstance(data, dict) or not isinstance(data.get("accepted"), bool):
            return {"accepted": False}
        return data

    def run_once(
        self,
        handler: Callable[[ClaimedStep], dict[str, Any]],
        *,
        cancel_aware_handler: Callable[[ClaimedStep, Event], dict[str, Any]] | None = None,
        worker_stop_event: Event | None = None,
    ) -> str:
        """Run one claimed step; cancel-aware engines receive an event set on lease loss.

        Legacy handlers remain supported. Engine adapters that own long-running
        external runs should use cancel_aware_handler and stop upstream work
        promptly when cancellation is signaled.
        """
        step = self.claim()
        if step is None:
            return "idle"
        try:
            if not self.renew(step):
                return "lease_lost"
        except Exception:
            # A failed initial renewal is not proof of lease ownership.
            return "lease_lost"

        heartbeat_stop = Event()
        lease_lost = Event()
        cancel_event = Event()

        def maintain_lease() -> None:
            next_renewal = monotonic() + self.heartbeat_interval_seconds
            while not heartbeat_stop.is_set():
                # Poll the shutdown signal more frequently than the lease heartbeat
                # so long-running engines receive a prompt cooperative cancellation.
                if worker_stop_event is not None and worker_stop_event.is_set():
                    cancel_event.set()
                    return
                remaining = max(0.0, next_renewal - monotonic())
                if heartbeat_stop.wait(min(0.25, remaining)):
                    return
                # Re-check shutdown after waking: a stop signal during the wait
                # must not trigger a needless renewal that consumes a fail RPC mock
                # response or turns an orderly shutdown into a lease-lost result.
                if worker_stop_event is not None and worker_stop_event.is_set():
                    cancel_event.set()
                    return
                if monotonic() < next_renewal:
                    continue
                try:
                    renewed = self.renew(step)
                    if not renewed:
                        if worker_stop_event is not None and worker_stop_event.is_set():
                            cancel_event.set()
                            return
                        lease_lost.set()
                        cancel_event.set()
                        return
                    next_renewal = monotonic() + self.heartbeat_interval_seconds
                except Exception:
                    # Shutdown cancellation still attempts a token-checked fail RPC;
                    # a lost lease is confirmed by that RPC rather than this heartbeat.
                    if worker_stop_event is not None and worker_stop_event.is_set():
                        cancel_event.set()
                        return
                    lease_lost.set()
                    cancel_event.set()
                    return

        heartbeat = Thread(
            target=maintain_lease,
            name=f"suly-lease-{step.step_id}",
            daemon=True,
        )
        heartbeat.start()
        # A stuck network/RPC call in the heartbeat must not hold the worker
        # forever. If it cannot stop promptly, ownership is treated as lost.
        heartbeat_join_timeout = max(
            0.1, min(5.0, self.heartbeat_interval_seconds * 2)
        )

        def stop_heartbeat() -> bool:
            heartbeat_stop.set()
            heartbeat.join(timeout=heartbeat_join_timeout)
            if heartbeat.is_alive():
                lease_lost.set()
                cancel_event.set()
                return False
            return True

        try:
            if cancel_aware_handler is not None:
                output = cancel_aware_handler(step, cancel_event)
            else:
                output = handler(step)
            if not isinstance(output, dict):
                raise TypeError("A task handler must return a JSON object.")
            try:
                output_bytes = json.dumps(
                    output, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ValueError("worker_output_invalid") from exc
            if len(output_bytes) > _MAX_OUTPUT_BYTES:
                raise ValueError("worker_output_too_large")
        except Exception:
            if not stop_heartbeat() or lease_lost.is_set():
                return "lease_lost"
            # Exception text may contain prompts, provider payloads, or secrets.
            shutdown_requested = worker_stop_event is not None and worker_stop_event.is_set()
            try:
                failure_result = self.fail(
                    step,
                    "worker_shutdown" if shutdown_requested else "tool_execution_failed",
                    (
                        "Worker is shutting down; the task step will be retried safely."
                        if shutdown_requested
                        else "Step execution failed. Sensitive diagnostic details were not stored"
                    ),
                )
            except Exception:
                # A failed failure-write must never be reported as durably recorded.
                return "failure_not_recorded"
            return (
                "failed_or_retry_scheduled"
                if failure_result.get("accepted") is True
                else "failure_not_recorded"
            )
        finally:
            # The join is bounded: a stalled heartbeat must never block this worker.
            stop_heartbeat()

        if lease_lost.is_set():
            return "lease_lost"
        # عند إيقاف الخدمة نعيد الخطوة للطابور عبر مسار الفشل القابل لإعادة المحاولة.
        # لا نعتمد نتيجة جزئية ولا نترك المهمة running حتى انتهاء lease.
        if worker_stop_event is not None and worker_stop_event.is_set():
            try:
                shutdown_result = self.fail(
                    step,
                    "worker_shutdown",
                    "Worker is shutting down; the task step will be retried safely.",
                )
            except Exception:
                return "failure_not_recorded"
            return "failed_or_retry_scheduled" if shutdown_result.get("accepted") is True else "failure_not_recorded"
        try:
            completed = self.complete(step, output)
        except Exception:
            # The RPC may have committed before the connection failed; do not
            # claim either success or lease loss without a confirmed response.
            return "completion_unconfirmed"
        return "completed" if completed else "lease_lost"
