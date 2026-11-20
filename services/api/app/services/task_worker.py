"""Trusted worker-side RPC adapter for durable SULY task steps.

This module deliberately does not start a daemon or deploy a worker. It is the
small execution boundary a separately hosted worker process can call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from supabase import Client


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

    def __init__(self, client: Client, worker_id: str, lease_seconds: int = 90) -> None:
        normalized = worker_id.strip()
        if not normalized or len(normalized) > 120:
            raise ValueError("worker_id must contain 1–120 non-whitespace characters")
        if not 15 <= lease_seconds <= 900:
            raise ValueError("lease_seconds must be between 15 and 900")
        self._client = client
        self.worker_id = normalized
        self.lease_seconds = lease_seconds

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
        raw_input = data.get("input") or {}
        if not isinstance(raw_input, dict):
            raise ValueError("worker_claim_invalid_input")
        attempt_count = int(data["attempt_count"])
        max_attempts = int(data["max_attempts"])
        if not 1 <= attempt_count <= max_attempts <= 10:
            raise ValueError("worker_claim_invalid_attempt_bounds")
        step_key = str(data["step_key"])
        title = str(data["title"])
        description = str(data.get("description") or "")
        if not step_key or len(step_key) > 100 or not title.strip() or len(title) > 200:
            raise ValueError("worker_claim_invalid_step_metadata")
        if len(description) > 4000:
            raise ValueError("worker_claim_invalid_step_metadata")
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
            lease_expires_at=str(data["lease_expires_at"]),
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
        return bool(response.data)

    def complete(self, step: ClaimedStep, output: dict[str, Any]) -> bool:
        response = self._client.rpc(
            "complete_task_step",
            {
                "p_step_id": str(step.step_id),
                "p_lease_token": str(step.lease_token),
                "p_output": output,
            },
        ).execute()
        return bool(response.data)

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
        return response.data or {"accepted": False}

    def run_once(self, handler: Callable[[ClaimedStep], dict[str, Any]]) -> str:
        """Claim and execute at most one step; handlers may call renew for long work."""
        step = self.claim()
        if step is None:
            return "idle"
        # Revalidate the lease immediately before invoking a handler. This also
        # observes a cancellation or lease revocation that raced with the claim.
        if not self.renew(step):
            return "lease_lost"
        try:
            output = handler(step)
            if not isinstance(output, dict):
                raise TypeError("A task handler must return a JSON object.")
        except Exception:
            # Exception text can contain user content, provider payloads, or secrets.
            # Persist a stable public-safe failure marker; keep raw diagnostics out
            # of task records and client-visible error fields.
            self.fail(
                step,
                "tool_execution_failed",
                "Step execution failed. Sensitive diagnostic details were not stored.",
            )
            return "failed_or_retry_scheduled"
        return "completed" if self.complete(step, output) else "lease_lost"
