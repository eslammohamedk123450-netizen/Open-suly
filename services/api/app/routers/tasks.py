from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.agent_planner import UnsupportedTaskRequest, plan_request, validate_agent_plan
from app.services.hermes_agent import HermesAgentError, HermesAgentUnavailable, resolve_agent_approval, steer_agent_run

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])
logger = logging.getLogger("suly.api.tasks")


class CreateTaskRequest(BaseModel):
    request: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=128)


class TaskPlanStep(BaseModel):
    step_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    depends_on: list[str] = Field(default_factory=list, max_length=32)
    input: dict[str, Any] = Field(default_factory=dict)


class CreateTaskPlanRequest(BaseModel):
    steps: list[TaskPlanStep] = Field(min_length=1, max_length=32)


class SteerEngineRunRequest(BaseModel):
    input: str = Field(min_length=1, max_length=20000)


class ResolveEngineApprovalRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_.:@-]+$")
    choice: str = Field(pattern=r"^(once|deny)$")


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

    try:
        normalized = validate_agent_plan(normalized)
    except UnsupportedTaskRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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


@router.post("/{task_id}/auto-plan")
def auto_plan_task(
    task_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a deterministic plan only for an operation the worker can run."""
    client = _admin_client()
    try:
        with client:
            task = _owned_task(client, task_id, user.id)
            if task.get("status") != "queued":
                raise HTTPException(status_code=409, detail="Only queued, unplanned tasks can be planned.")
            try:
                planned = plan_request(str(task.get("request") or ""))
            except UnsupportedTaskRequest as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            result = client.rpc(
                "plan_task",
                {
                    "p_task_id": str(task_id),
                    "p_user_id": user.id,
                    "p_steps": planned.steps,
                },
            ).execute().data
        if isinstance(result, list) and result:
            result = result[0]
        if not isinstance(result, dict):
            raise HTTPException(status_code=503, detail="The task planner returned an invalid result.")
        return {**result, "planner": planned.planner, "steps": planned.steps}
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "task_not_found" in message:
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        if "task_already_planned" in message:
            raise HTTPException(status_code=409, detail="Task has already been planned.") from exc
        raise HTTPException(status_code=503, detail="Could not create task plan.") from exc


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
                .select("id,task_id,user_id,step_key,title,description,step_order,depends_on,status,input,output,error_code,error_message,attempt_count,max_attempts,started_at,completed_at,created_at,updated_at")
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .order("step_order")
                .execute()
                .data
            )
            engine_runs = (
                client.table("engine_runs")
                .select("id,task_id,step_id,attempt_count,engine_id,status,error_code,started_at,completed_at,created_at,updated_at")
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
                .data
            )
            engine_events = (
                client.table("engine_run_events")
                .select("id,engine_run_id,task_id,event_name,event_seq,event_timestamp,received_at")
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .order("received_at")
                .order("id")
                .limit(500)
                .execute()
                .data
            )
        return {
            "task": task,
            "steps": steps or [],
            "engine_runs": engine_runs or [],
            "engine_events": engine_events or [],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load task.") from exc



@router.post("/{task_id}/engine-runs/{run_id}/steer")
def steer_task_engine_run(
    task_id: UUID,
    run_id: UUID,
    request: SteerEngineRunRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Allow the authenticated task owner to steer only their active Hermes run."""
    client = _admin_client()
    try:
        with client:
            task = _owned_task(client, task_id, user.id)
            if task.get("status") != "running":
                raise HTTPException(status_code=409, detail="Only a running task can receive steering input.")

            runs = (
                client.table("engine_runs")
                .select("id,step_id,engine_id,status,upstream_run_id")
                .eq("id", str(run_id))
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not runs:
                raise HTTPException(status_code=404, detail="Engine run not found.")
            engine_run = runs[0]
            upstream_run_id = engine_run.get("upstream_run_id")
            if (
                engine_run.get("engine_id") != "hermes-agent"
                or engine_run.get("status") != "running"
                or not isinstance(upstream_run_id, str)
            ):
                raise HTTPException(status_code=409, detail="This engine run is not accepting steering input.")

            settings = get_settings()
            if (
                not settings.worker_enabled
                or not settings.hermes_agent_enabled
                or not settings.hermes_agent_isolation_confirmed
                or not settings.hermes_agent_base_url
                or settings.hermes_agent_api_key is None
            ):
                raise HTTPException(status_code=503, detail="Hermes steering is not available.")

            steps = (
                client.table("task_steps")
                .select("id,lease_token,status")
                .eq("id", str(engine_run["step_id"]))
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not steps or steps[0].get("status") != "running" or not steps[0].get("lease_token"):
                raise HTTPException(status_code=409, detail="The task worker no longer owns this run.")

            try:
                steer_agent_run(upstream_run_id, request.input)
            except HermesAgentUnavailable as exc:
                raise HTTPException(status_code=503, detail="Hermes steering is unavailable.") from exc
            except HermesAgentError as exc:
                raise HTTPException(status_code=502, detail="Hermes did not accept the steering request.") from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="The steering request is invalid.") from exc

            # Store only a metadata event. The RPC re-checks the lease to close races
            # between the owner check above and the upstream control request.
            try:
                client.rpc("append_engine_run_event", {
                    "p_run_id": str(run_id),
                    "p_step_id": str(engine_run["step_id"]),
                    "p_lease_token": str(steps[0]["lease_token"]),
                    "p_event_name": "run.steered",
                    "p_event_seq": None,
                    "p_event_timestamp": None,
                }).execute()
            except Exception:
                logger.warning("Could not persist Hermes steering metadata for engine run %s", run_id)

        return {"task_id": str(task_id), "engine_run_id": str(run_id), "accepted": True}
    except HTTPException:
        raise
    except Exception as exc:
        if "task_not_found" in str(exc):
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        raise HTTPException(status_code=503, detail="Could not steer the engine run.") from exc


@router.post("/{task_id}/engine-runs/{run_id}/approvals")
def resolve_task_engine_approval(
    task_id: UUID,
    run_id: UUID,
    request: ResolveEngineApprovalRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Resolve one exact pending Hermes approval; SULY exposes once/deny only."""
    client = _admin_client()
    try:
        with client:
            task = _owned_task(client, task_id, user.id)
            if task.get("status") != "running":
                raise HTTPException(status_code=409, detail="Only a running task can receive an approval response.")

            runs = (
                client.table("engine_runs")
                .select("id,step_id,engine_id,status,upstream_run_id")
                .eq("id", str(run_id))
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not runs:
                raise HTTPException(status_code=404, detail="Engine run not found.")
            engine_run = runs[0]
            upstream_run_id = engine_run.get("upstream_run_id")
            if (
                engine_run.get("engine_id") != "hermes-agent"
                or engine_run.get("status") != "running"
                or not isinstance(upstream_run_id, str)
            ):
                raise HTTPException(status_code=409, detail="This Hermes run is not active.")

            request_events = (
                client.table("engine_run_events")
                .select("id,approval_request_id")
                .eq("engine_run_id", str(run_id))
                .eq("event_name", "approval.request")
                .eq("approval_request_id", request.request_id)
                .limit(1)
                .execute()
                .data
            )
            if not request_events:
                raise HTTPException(status_code=404, detail="Pending approval request not found.")

            prior_responses = (
                client.table("engine_run_events")
                .select("id")
                .eq("engine_run_id", str(run_id))
                .eq("event_name", "approval.responded")
                .eq("approval_request_id", request.request_id)
                .limit(1)
                .execute()
                .data
            )
            if prior_responses:
                raise HTTPException(status_code=409, detail="This approval request has already been answered.")

            settings = get_settings()
            if (
                not settings.worker_enabled
                or not settings.hermes_agent_enabled
                or not settings.hermes_agent_isolation_confirmed
                or not settings.hermes_agent_base_url
                or settings.hermes_agent_api_key is None
            ):
                raise HTTPException(status_code=503, detail="Hermes approvals are not available.")

            steps = (
                client.table("task_steps")
                .select("id,lease_token,status")
                .eq("id", str(engine_run["step_id"]))
                .eq("task_id", str(task_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            )
            if not steps or steps[0].get("status") != "running" or not steps[0].get("lease_token"):
                raise HTTPException(status_code=409, detail="The task worker no longer owns this run.")

            try:
                resolve_agent_approval(upstream_run_id, request.request_id, request.choice)
            except HermesAgentUnavailable as exc:
                raise HTTPException(status_code=503, detail="Hermes approvals are unavailable.") from exc
            except HermesAgentError as exc:
                raise HTTPException(status_code=409, detail="Hermes could not resolve this approval request.") from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="The approval response is invalid.") from exc

            try:
                persisted = client.rpc("append_engine_run_event", {
                    "p_run_id": str(run_id),
                    "p_step_id": str(engine_run["step_id"]),
                    "p_lease_token": str(steps[0]["lease_token"]),
                    "p_event_name": "approval.responded",
                    "p_event_seq": None,
                    "p_event_timestamp": None,
                    "p_approval_request_id": request.request_id,
                    "p_approval_choice": request.choice,
                }).execute().data
                if persisted is not True:
                    logger.warning("Hermes approval was resolved after task lease loss for engine run %s", run_id)
            except Exception:
                logger.warning("Could not persist Hermes approval metadata for engine run %s", run_id)

        return {
            "task_id": str(task_id),
            "engine_run_id": str(run_id),
            "request_id": request.request_id,
            "choice": request.choice,
            "accepted": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        if "task_not_found" in str(exc):
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        raise HTTPException(status_code=503, detail="Could not resolve the engine approval.") from exc


@router.post("/{task_id}/retry")
def retry_failed_task(
    task_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retry failed steps for an owned task, within the persisted retry limit."""
    client = _admin_client()
    try:
        with client:
            result = client.rpc(
                "retry_failed_task",
                {"p_task_id": str(task_id), "p_user_id": user.id},
            ).execute().data
        if isinstance(result, list) and result:
            result = result[0]
        if not isinstance(result, dict):
            raise HTTPException(status_code=503, detail="The retry service returned an invalid result.")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "task_not_found" in message:
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        if "task_not_failed" in message:
            raise HTTPException(status_code=409, detail="Only failed tasks can be retried.") from exc
        if "manual_retry_limit_reached" in message:
            raise HTTPException(status_code=409, detail="The manual retry limit has been reached.") from exc
        if "no_failed_steps_to_retry" in message:
            raise HTTPException(status_code=409, detail="This task has no failed steps to retry.") from exc
        raise HTTPException(status_code=503, detail="Could not retry the task.") from exc


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
                    .in_("status", ["queued", "planning", "ready", "running", "waiting_approval"])
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
