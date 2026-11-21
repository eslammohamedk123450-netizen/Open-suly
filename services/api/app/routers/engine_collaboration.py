"""Owner-scoped API for explicit, approved cross-engine task handoffs."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client

router = APIRouter(prefix="/v1/tasks", tags=["engine-collaboration"])


class CreateEngineHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_engine: Literal["hermes-agent", "opencode"]
    capability: str = Field(min_length=2, max_length=96, pattern=r"^[a-z][a-z0-9_.-]{1,95}$")
    prompt: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    max_child_tasks: int = Field(default=1, ge=1, le=8)
    max_parallel_children: int = Field(default=1, ge=1, le=2)
    max_runtime_seconds: int = Field(default=300, ge=1, le=1800)
    max_input_bytes: int = Field(default=64000, ge=1, le=64000)


def _admin_client():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collaboration service is not configured.",
        )
    return client


def _owned_task(client: Any, task_id: UUID, user_id: str) -> dict[str, Any]:
    rows = (
        client.table("tasks")
        .select("id,user_id,status,project_id")
        .eq("id", str(task_id))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found.")
    return rows[0]


def _owned_handoff(
    client: Any, task_id: UUID, handoff_id: UUID, user_id: str
) -> dict[str, Any]:
    rows = (
        client.table("engine_collaboration_handoffs")
        .select("id,parent_task_id,user_id,status,target_engine,child_task_id")
        .eq("id", str(handoff_id))
        .eq("parent_task_id", str(task_id))
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Collaboration handoff not found.")
    return rows[0]


def _rpc_value(data: Any) -> Any:
    if isinstance(data, list):
        return data[0] if data else None
    return data


def _raise_collaboration_error(exc: Exception) -> None:
    message = str(exc).lower()
    if "not_found" in message:
        raise HTTPException(status_code=404, detail="Task or handoff not found.") from exc
    if any(code in message for code in (
        "not_running", "not_pending", "budget_exceeded", "parallel_limit",
        "idempotency_conflict", "budget_mismatch", "not_cancellable", "engine_pair_invalid",
    )):
        raise HTTPException(status_code=409, detail="The collaboration state no longer permits this action.") from exc
    if any(code in message for code in (
        "request_invalid", "payload_invalid", "title_invalid",
        "capability_not_supported", "project_required", "depth_exceeded",
    )):
        raise HTTPException(status_code=422, detail="The collaboration request is invalid or unsupported.") from exc
    raise HTTPException(status_code=503, detail="Collaboration operation failed.") from exc


@router.post("/{task_id}/engine-runs/{run_id}/handoffs", status_code=status.HTTP_202_ACCEPTED)
def create_engine_handoff(
    task_id: UUID,
    run_id: UUID,
    request: CreateEngineHandoffRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a pending handoff from one running engine attempt; no child runs before approval."""
    client = _admin_client()
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Delegated prompt cannot be blank.")
    payload: dict[str, str] = {"prompt": prompt}
    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Delegated task title cannot be blank.")
        payload["title"] = title

    try:
        with client:
            _owned_task(client, task_id, user.id)
            response = client.rpc(
                "create_engine_collaboration_handoff",
                {
                    "p_parent_task_id": str(task_id),
                    "p_parent_run_id": str(run_id),
                    "p_user_id": user.id,
                    "p_target_engine": request.target_engine,
                    "p_capability": request.capability,
                    "p_idempotency_key": request.idempotency_key,
                    "p_input_payload": payload,
                    "p_max_child_tasks": request.max_child_tasks,
                    "p_max_parallel_children": request.max_parallel_children,
                    "p_max_runtime_seconds": request.max_runtime_seconds,
                    "p_max_input_bytes": request.max_input_bytes,
                },
            ).execute()
            handoff_id = _rpc_value(response.data)
            if handoff_id is None:
                raise RuntimeError("collaboration_create_invalid_response")
            rows = (
                client.table("engine_collaboration_handoffs")
                .select("id,status,target_engine,capability,created_at")
                .eq("id", str(handoff_id))
                .eq("parent_task_id", str(task_id))
                .eq("user_id", user.id)
                .limit(1)
                .execute()
                .data
            ) or []
        if not rows:
            raise RuntimeError("collaboration_create_result_not_found")
        return {"handoff": rows[0]}
    except HTTPException:
        raise
    except Exception as exc:
        _raise_collaboration_error(exc)


@router.get("/{task_id}/collaboration")
def list_task_collaboration(
    task_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List only this owner's handoffs and metadata-only events for one parent task."""
    client = _admin_client()
    try:
        with client:
            _owned_task(client, task_id, user.id)
            handoffs = (
                client.table("engine_collaboration_handoffs")
                .select(
                    "id,parent_task_id,child_task_id,parent_run_id,source_engine,target_engine,"
                    "capability,status,depth,max_child_tasks,max_parallel_children,"
                    "max_runtime_seconds,max_input_bytes,approved_at,started_at,"
                    "finished_at,error_code,created_at,updated_at"
                )
                .eq("parent_task_id", str(task_id))
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
                .data
            ) or []
            handoff_ids = [str(item["id"]) for item in handoffs]
            events = []
            if handoff_ids:
                events = (
                    client.table("engine_collaboration_events")
                    .select("id,handoff_id,sequence,event_type,status,metadata,created_at")
                    .in_("handoff_id", handoff_ids)
                    .eq("user_id", user.id)
                    .order("sequence")
                    .limit(500)
                    .execute()
                    .data
                ) or []
        by_handoff: dict[str, list[dict[str, Any]]] = {item: [] for item in handoff_ids}
        for event in events:
            key = str(event.get("handoff_id", ""))
            if key in by_handoff:
                by_handoff[key].append(event)
        return {
            "items": [
                {**item, "events": by_handoff.get(str(item["id"]), [])}
                for item in handoffs
            ]
        }
    except HTTPException:
        raise
    except Exception as exc:
        _raise_collaboration_error(exc)


@router.post("/{task_id}/collaboration/{handoff_id}/approve", status_code=status.HTTP_202_ACCEPTED)
def approve_task_collaboration(
    task_id: UUID,
    handoff_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Require a fresh owner action, then atomically enqueue one ordinary SULY child task."""
    client = _admin_client()
    try:
        with client:
            _owned_task(client, task_id, user.id)
            _owned_handoff(client, task_id, handoff_id, user.id)
            response = client.rpc(
                "approve_engine_collaboration_handoff",
                {"p_handoff_id": str(handoff_id), "p_user_id": user.id},
            ).execute()
            result = _rpc_value(response.data)
        if not isinstance(result, dict) or not result.get("child_task_id"):
            raise RuntimeError("collaboration_approval_invalid_response")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _raise_collaboration_error(exc)


@router.post("/{task_id}/collaboration/{handoff_id}/reject")
def reject_task_collaboration(
    task_id: UUID,
    handoff_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, bool]:
    client = _admin_client()
    try:
        with client:
            _owned_task(client, task_id, user.id)
            _owned_handoff(client, task_id, handoff_id, user.id)
            response = client.rpc(
                "reject_engine_collaboration_handoff",
                {"p_handoff_id": str(handoff_id), "p_user_id": user.id},
            ).execute()
        if _rpc_value(response.data) is not True:
            raise HTTPException(status_code=409, detail="Collaboration handoff could not be rejected.")
        return {"rejected": True}
    except HTTPException:
        raise
    except Exception as exc:
        _raise_collaboration_error(exc)


@router.post("/{task_id}/collaboration/{handoff_id}/cancel")
def cancel_task_collaboration(
    task_id: UUID,
    handoff_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, bool]:
    client = _admin_client()
    try:
        with client:
            _owned_task(client, task_id, user.id)
            _owned_handoff(client, task_id, handoff_id, user.id)
            response = client.rpc(
                "cancel_engine_collaboration_handoff",
                {"p_handoff_id": str(handoff_id), "p_user_id": user.id},
            ).execute()
        if _rpc_value(response.data) is not True:
            raise HTTPException(status_code=409, detail="Collaboration handoff could not be cancelled.")
        return {"cancel_requested": True}
    except HTTPException:
        raise
    except Exception as exc:
        _raise_collaboration_error(exc)
