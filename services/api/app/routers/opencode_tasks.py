"""Authenticated read and approval endpoints for OpenCode task runs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client
from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore
from app.services.opencode_approval_manager import OpenCodeApprovalManager

router = APIRouter(prefix="/v1", tags=["opencode-tasks"])


class ChangeSetDecision(BaseModel):
    decision: str = Field(pattern=r"^(apply|reject)$")


class PermissionDecision(BaseModel):
    decision: str = Field(pattern=r"^(once|reject)$")


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


def _release_runtime_for_run(request: Request, client, user_id: str, run_id: str) -> None:
    broker = getattr(request.app.state, "runtime_broker", None)
    if broker is None:
        return
    rows = client.table("opencode_task_runs").select(
        "task_id,engine_run_id"
    ).eq("id", run_id).eq("user_id", user_id).limit(1).execute().data
    if rows:
        released = broker.release_attempt(rows[0]["task_id"], rows[0]["engine_run_id"], "opencode")
        if not released:
            # Provisioner TTL cleanup remains the fallback after worker restart.
            pass


def _active_runtime_lease(request: Request, run_row: dict[str, Any]):
    broker = getattr(request.app.state, "runtime_broker", None)
    if broker is None:
        raise HTTPException(status_code=503, detail="OpenCode runtime broker is not configured.")
    lease = broker.lease_for_attempt(
        run_row["task_id"], run_row["engine_run_id"], "opencode"
    )
    if lease is None:
        raise HTTPException(status_code=409, detail="OpenCode runtime is no longer active.")
    return lease


@router.post("/opencode/approvals/{approval_id}/decision")
def decide_permission(
    approval_id: UUID,
    body: PermissionDecision,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Dispatch only once/reject to the active lease bound to the owning task attempt."""
    try:
        client = _client()
        rows = client.table("opencode_approvals").select(
            "id,run_id,session_id"
        ).eq("id", str(approval_id)).eq("user_id", user.id).eq(
            "status", "pending"
        ).limit(1).execute().data
        if not rows:
            raise HTTPException(status_code=404, detail="Pending permission request not found.")
        run_rows = client.table("opencode_task_runs").select(
            "task_id,engine_run_id"
        ).eq("id", rows[0]["run_id"]).eq("user_id", user.id).limit(1).execute().data
        if not run_rows:
            raise HTTPException(status_code=404, detail="OpenCode task run not found.")
        lease = _active_runtime_lease(request, run_rows[0])
        store = OpenCodeLifecycleStore(client)
        accepted = OpenCodeApprovalManager(store=store).decide(
            user_id=user.id, approval_id=str(approval_id), decision=body.decision,
            base_url=lease.base_url, gateway_path=lease.gateway_path,
            runtime_token=lease.access_token,
        )
        if not accepted:
            raise HTTPException(status_code=409, detail="Permission request was already decided.")
        return {"accepted": True, "approval_id": str(approval_id), "decision": body.decision}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not dispatch OpenCode permission decision.") from exc


@router.get("/opencode/runs/{run_id}/approvals")
def list_run_approvals(
    run_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Refresh and list pending permission prompts for this owner's active task run."""
    try:
        client = _client()
        run_rows = client.table("opencode_task_runs").select(
            "task_id,engine_run_id,upstream_session_id"
        ).eq("id", str(run_id)).eq("user_id", user.id).limit(1).execute().data
        if not run_rows:
            raise HTTPException(status_code=404, detail="OpenCode task run not found.")
        run = run_rows[0]
        broker = getattr(request.app.state, "runtime_broker", None)
        if broker is not None and run.get("upstream_session_id"):
            lease = broker.lease_for_attempt(run["task_id"], run["engine_run_id"], "opencode")
            if lease is not None:
                OpenCodeApprovalManager(store=OpenCodeLifecycleStore(client)).collect_pending(
                    user_id=user.id, run_id=str(run_id),
                    session_id=run["upstream_session_id"], base_url=lease.base_url,
                    gateway_path=lease.gateway_path, runtime_token=lease.access_token,
                )
        rows = OpenCodeLifecycleStore(client).list_pending_approvals(
            user_id=user.id, run_id=str(run_id), limit=limit
        )
        return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load OpenCode approvals.") from exc


@router.get("/opencode/change-sets/{change_set_id}")
def get_change_set(
    change_set_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return only this owner's reviewable change set and its file diff payload."""
    try:
        rows = (_client().table("opencode_change_sets")
            .select("id,run_id,project_id,base_revision,status,changes,created_at,decided_at")
            .eq("id", str(change_set_id)).eq("user_id", user.id)
            .limit(1).execute().data or [])
        if not rows:
            raise HTTPException(status_code=404, detail="Change set not found.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load OpenCode change set.") from exc


@router.post("/opencode/change-sets/{change_set_id}/decision")
def decide_change_set(
    change_set_id: UUID,
    body: ChangeSetDecision,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Apply atomically against the captured revision, or reject the pending set."""
    try:
        client = _client()
        owned = client.table("opencode_change_sets").select(
            "id,run_id"
        ).eq("id", str(change_set_id)).eq("user_id", user.id).eq(
            "status", "review_ready"
        ).limit(1).execute().data
        if not owned:
            raise HTTPException(status_code=404, detail="Change set not found or already decided.")
        run_id = owned[0]["run_id"]
        store = OpenCodeLifecycleStore(client)
        if body.decision == "apply":
            result = store.apply_change_set(
                user_id=user.id, change_set_id=str(change_set_id)
            )
            if not result["applied"] and result.get("reason") == "workspace_revision_conflict":
                raise HTTPException(status_code=409, detail="Project changed after this result was prepared.")
            if not result["applied"]:
                raise HTTPException(status_code=409, detail="Change set is no longer reviewable.")
            _release_runtime_for_run(request, client, user.id, run_id)
            return result
        rows = client.table("opencode_change_sets").update({
            "status": "rejected",
        }).eq("id", str(change_set_id)).eq("user_id", user.id).eq(
            "status", "review_ready"
        ).execute().data
        if not rows:
            raise HTTPException(status_code=404, detail="Change set not found or already decided.")
        _release_runtime_for_run(request, client, user.id, run_id)
        return {"applied": False, "rejected": True, "change_set_id": str(change_set_id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not decide OpenCode change set.") from exc
