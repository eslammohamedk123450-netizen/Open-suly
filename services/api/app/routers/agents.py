"""Authenticated read-only catalog of SULY agent roles and Hermes capabilities."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import AuthenticatedUser, get_current_user
from app.services.hermes_catalog import (
    HermesCatalogError,
    HermesCatalogUnavailable,
    get_hermes_skill_catalog,
    get_hermes_toolset_catalog,
)
from app.worker_runtime import build_agent_manager, build_engine_registry

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("")
def list_agents(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return public agent capabilities, never provider credentials or runtime secrets."""
    del user  # Authentication is required; the catalog contains no user-specific secrets.
    registry = build_engine_registry(
        idempotency_key="agent-catalog-read",
        on_run_started=lambda _run_id: False,
    )
    manager = build_agent_manager(registry)
    items = []
    for agent in manager.list():
        engines = sorted({
            engine.engine_id
            for capability in agent.capabilities
            for engine in registry.candidates(capability)
        })
        items.append({
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
            "capabilities": sorted(agent.capabilities),
            "enabled": agent.enabled,
            "available": bool(engines),
            "requires_approval": agent.requires_approval,
            "engines": engines,
        })
    return {"items": items}


@router.get("/hermes/skills")
async def list_hermes_skills(
    _user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return bounded skill metadata only; never return skill source or install controls."""
    try:
        return await get_hermes_skill_catalog()
    except HermesCatalogUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HermesCatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/hermes/toolsets")
async def list_hermes_toolsets(
    _user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return bounded toolset metadata only; never expose config secrets or execute tools."""
    try:
        return await get_hermes_toolset_catalog()
    except HermesCatalogUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HermesCatalogError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
