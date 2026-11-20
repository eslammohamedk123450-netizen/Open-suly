"""Authenticated read and approval endpoints for OpenCode task runs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client
from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore

router = APIRouter(prefix="/v1", tags=["opencode-tasks"])


class ChangeSetDecision(BaseModel):
    decision: str = Field(pattern=r"^(apply|reject)$")


def _client():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="OpenCode task service is not configured.")
    return client


@router.get("/projects/{project_id}/opencode/runs")
def list_project_runs(
    project_id: UUID,
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List only task metadata belonging to the authenticated user's project."""
    try:
        rows = (_client().table("opencode_task_runs")
            .select("id,project_id,task_id,engine_run_id,runtime_id,upstream_session_id,status,workspace_revision,error_code,started_at,finished_at,created_at,updated_at")
            .eq("user_id", user.id).eq("project_id", str(project_id))
            .order("created_at", desc=True).limit(limit).execute().data or [])
        return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load OpenCode task runs.") from exc


@router.get("/opencode/runs/{run_id}/events")
def list_run_events(
    run_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return sanitized lifecycle events after confirming run ownership."""
    try:
        client = _client()
        owned = client.table("opencode_task_runs").select("id").eq(
            "id", str(run_id)
        ).eq("user_id", user.id).limit(1).execute().data
        if not owned:
            raise HTTPException(status_code=404, detail="OpenCode task run not found.")
        rows = (client.table("opencode_task_events")
            .select("sequence,event_type,payload,created_at")
            .eq("run_id", str(run_id)).eq("user_id", user.id)
            .order("sequence").limit(limit).execute().data or [])
        return {"items": rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load OpenCode task events.") from exc


@router.get("/opencode/runs/{run_id}/approvals")
def list_run_approvals(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List pending permission prompts for this owner's task run."""
    try:
        rows = OpenCodeLifecycleStore(_client()).list_pending_approvals(
            user_id=user.id, run_id=str(run_id), limit=limit
        )
        return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load OpenCode approvals.") from exc


@router.post("/opencode/change-sets/{change_set_id}/decision")
def decide_change_set(
    change_set_id: UUID,
    body: ChangeSetDecision,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Apply with an atomic workspace revision check, or reject a pending change set."""
    try:
        store = OpenCodeLifecycleStore(_client())
        if body.decision == "apply":
            result = store.apply_change_set(
                user_id=user.id, change_set_id=str(change_set_id)
            )
            if not result["applied"] and result.get("reason") == "workspace_revision_conflict":
                raise HTTPException(status_code=409, detail="Project changed after this result was prepared.")
            if not result["applied"]:
                raise HTTPException(status_code=409, detail="Change set is no longer reviewable.")
            return result
        rows = (_client().table("opencode_change_sets").update({
            "status": "rejected",
        }).eq("id", str(change_set_id)).eq("user_id", user.id)
          .eq("status", "review_ready").execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="Change set not found or already decided.")
        return {"applied": False, "rejected": True, "change_set_id": str(change_set_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not decide OpenCode change set.") from exc
