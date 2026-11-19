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


class TaskPlanStep(BaseModel):
    step_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    input: dict[str, Any] = Field(default_factory=dict)


class CreateTaskPlanRequest(BaseModel):
    steps: list[TaskPlanStep] = Field(min_length=1, max_length=50)


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



@router.post("/{task_id}/plan")
def plan_task(
    task_id: UUID,
    request: CreateTaskPlanRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    # Dependencies must reference earlier unique keys, guaranteeing a DAG.
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for step in request.steps:
        if step.step_key in seen:
            raise HTTPException(status_code=422, detail="Step keys must be unique.")
        if len(set(step.depends_on)) != len(step.depends_on):
            raise HTTPException(status_code=422, detail="A step cannot repeat a dependency.")
        if any(dependency not in seen for dependency in step.depends_on):
            raise HTTPException(
                status_code=422,
                detail="Each dependency must reference a step declared earlier in the plan.",
            )
        seen.add(step.step_key)
        normalized.append(step.model_dump())

    client = _admin_client()
    try:
        with client:
            result = client.rpc(
                "plan_task",
                {"p_task_id": str(task_id), "p_user_id": user.id, "p_steps": normalized},
            ).execute().data
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
        raise HTTPException(status_code=503, detail="The task planner returned an invalid result.")
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "task_not_found" in message:
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        if "task_already_planned" in message:
            raise HTTPException(status_code=409, detail="Task has already been planned.") from exc
        if any(code in message for code in (
            "invalid_step_definition", "duplicate_step_key",
            "dependency_must_reference_prior_step", "plan_step_count_out_of_range",
        )):
            raise HTTPException(status_code=422, detail="The task plan is invalid.") from exc
        raise HTTPException(status_code=503, detail="Could not save task plan.") from exc


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
