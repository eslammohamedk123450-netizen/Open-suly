from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    request: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=128)


def _admin_client():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task service is not configured on the server.",
        )
    return client


def _owned_task(client: Any, task_id: UUID, user_id: str) -> dict[str, Any]:
    rows = (
        client.table("tasks")
        .select("*")
        .eq("id", str(task_id))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found.")
    return rows[0]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_task(
    request: CreateTaskRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    clean_request = request.request.strip()
    if not clean_request:
        raise HTTPException(status_code=422, detail="Task request cannot be blank.")
    title = (request.title or clean_request[:80]).strip() or clean_request[:80]
    client = _admin_client()
    try:
        with client:
            existing = (
                client.table("tasks")
                .select("*")
                .eq("user_id", user.id)
                .eq("idempotency_key", request.idempotency_key)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                return existing[0]

            payload = {
                "user_id": user.id,
                "title": title,
                "request": clean_request,
                "idempotency_key": request.idempotency_key,
            }
            try:
                inserted = client.table("tasks").insert(payload).execute().data
                if inserted:
                    return inserted[0]
            except Exception:
                # A concurrent retry may have created the same idempotency key.
                duplicate = (
                    client.table("tasks")
                    .select("*")
                    .eq("user_id", user.id)
                    .eq("idempotency_key", request.idempotency_key)
                    .limit(1)
                    .execute()
                    .data
                )
                if duplicate:
                    return duplicate[0]
                raise
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not enqueue task.") from exc
    raise HTTPException(status_code=503, detail="Could not enqueue task.")


@router.get("")
def list_tasks(
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin_client()
    try:
        with client:
            rows = (
                client.table("tasks")
                .select("*")
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
            )
        return {"items": rows or []}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load tasks.") from exc


@router.get("/{task_id}")
def get_task(
    task_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin_client()
    try:
        with client:
            task = _owned_task(client, task_id, user.id)
            steps = (
                client.table("task_steps")
                .select("*")
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .order("step_order")
                .execute()
                .data
            )
        return {"task": task, "steps": steps or []}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load task.") from exc


@router.post("/{task_id}/cancel")
def request_task_cancellation(
    task_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin_client()
    try:
        with client:
            task = _owned_task(client, task_id, user.id)
            if task["status"] in ("completed", "failed", "cancelled"):
                return task
            if task["status"] != "cancel_requested":
                updated = (
                    client.table("tasks")
                    .update({
                        "status": "cancel_requested",
                        "cancel_requested_at": datetime.now(timezone.utc).isoformat(),
                    })
                    .eq("id", str(task_id))
                    .eq("user_id", user.id)
                    .execute()
                    .data
                )
                if updated:
                    return updated[0]
            return _owned_task(client, task_id, user.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not request task cancellation.") from exc
