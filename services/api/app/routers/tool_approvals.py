"""Authenticated user consent and audit endpoints for registered tools."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.tool_approvals import ToolApprovalStore
from app.worker_runtime import TOOL_REGISTRY

router = APIRouter(prefix="/v1/tools/approvals", tags=["tool approvals"])


class ToolApprovalRequest(BaseModel):
    permission_scope: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")


def _store() -> ToolApprovalStore:
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tool approval service is not configured on the server.",
        )
    return ToolApprovalStore(client)


def _approvable_scope(scope: str) -> None:
    if not TOOL_REGISTRY.requires_approval_scope(scope):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This permission scope is not currently available for approval.",
        )


@router.get("")
def list_tool_approvals(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        store = _store()
        return {"items": store.list_approvals(user.id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load tool approvals.") from exc


@router.get("/events")
def list_tool_approval_events(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        store = _store()
        return {"items": store.list_events(user.id)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load tool approval history.") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def grant_tool_approval(
    request: ToolApprovalRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    scope = request.permission_scope.strip()
    _approvable_scope(scope)
    try:
        approval_id = _store().grant(user.id, scope)
        return {"id": approval_id, "permission_scope": scope, "active": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not save tool approval.") from exc


@router.delete("")
def revoke_tool_approval(
    request: ToolApprovalRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    scope = request.permission_scope.strip()
    _approvable_scope(scope)
    try:
        revoked = _store().revoke(user.id, scope)
        return {"permission_scope": scope, "revoked": revoked}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not revoke tool approval.") from exc



@router.get("/catalog")
def list_available_tools(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return registered worker tools and approval status for the current user."""
    try:
        approved_scopes = _store().active_scopes(user.id)
        settings = get_settings()
        ai_provider_configured = bool(
            settings.ai_base_url
            and settings.ai_model
            and (
                settings.ai_provider == "ollama"
                or (
                    settings.ai_provider == "openai-compatible"
                    and settings.ai_api_key
                )
            )
        )
        ai_provider_available = bool(settings.worker_enabled and ai_provider_configured)
        hermes_available = bool(
            settings.worker_enabled
            and settings.hermes_agent_enabled
            and settings.runtime_provisioner_url
            and settings.runtime_provisioner_token
            and settings.runtime_provisioner_allowed_origins
        )
        opencode_available = bool(
            settings.worker_enabled
            and getattr(settings, "opencode_enabled", False)
            and getattr(settings, "runtime_provisioner_url", None)
            and getattr(settings, "runtime_provisioner_token", None)
            and getattr(settings, "runtime_provisioner_allowed_origins", None)
        )
        items = []
        for tool in TOOL_REGISTRY.describe():
            if tool["name"] == "hermes.agent.turn":
                available = hermes_available  # Hermes has its own isolated runtime configuration.
            elif tool["name"] == "ai.respond":
                available = ai_provider_available
            elif tool["name"] == "opencode.task.run":
                available = opencode_available
            else:
                available = settings.worker_enabled
            items.append({
                **tool,
                "approved": (
                    not tool["requires_approval"]
                    or tool["permission_scope"] in approved_scopes
                ),
                "available": available,
            })
        return {"items": items}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load tool catalog.") from exc
