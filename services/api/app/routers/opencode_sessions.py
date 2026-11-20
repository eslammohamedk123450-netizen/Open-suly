"""Owner-scoped read API for durable OpenCode session metadata."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client
from app.services.opencode_session_store import OpenCodeSessionStore

router = APIRouter(prefix="/v1/projects", tags=["opencode-sessions"])


@router.get("/{project_id}/opencode/sessions")
def list_opencode_sessions(
    project_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List only metadata for the authenticated owner's project sessions."""
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="OpenCode session service is not configured.")
    try:
        with client:
            rows = OpenCodeSessionStore(client).list_project(
                user_id=user.id, project_id=str(project_id), limit=limit
            )
        return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load project sessions.") from exc
