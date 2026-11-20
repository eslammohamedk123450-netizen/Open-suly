"""Owner-scoped project workspace API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_change(self):
        if self.name is None and self.description is None:
            raise ValueError("At least one project field must be provided.")
        return self


def _admin():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Project service is not configured.")
    return client


def _clean_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name cannot be blank.")
    return name


@router.get("")
def list_projects(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    client = _admin()
    try:
        with client:
            rows = (client.table("projects")
                .select("id,user_id,name,description,created_at,updated_at")
                .eq("user_id", user.id).order("updated_at", desc=True)
                .limit(100).execute().data)
        return {"items": rows or []}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load projects.") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(request: CreateProjectRequest, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    client = _admin()
    try:
        with client:
            rows = client.table("projects").insert({
                "user_id": user.id,
                "name": _clean_name(request.name),
                "description": request.description.strip(),
            }).execute().data
        if not rows:
            raise HTTPException(status_code=503, detail="Project was not created.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not create project.") from exc


@router.patch("/{project_id}")
def update_project(project_id: UUID, request: UpdateProjectRequest, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    values = request.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is not None:
        values["name"] = _clean_name(values["name"])
    if "description" in values and values["description"] is not None:
        values["description"] = values["description"].strip()
    values["updated_at"] = datetime.now(timezone.utc).isoformat()
    client = _admin()
    try:
        with client:
            rows = (client.table("projects").update(values).eq("id", str(project_id))
                .eq("user_id", user.id).execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="Project not found.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not update project.") from exc


@router.delete("/{project_id}")
def delete_project(project_id: UUID, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, bool]:
    client = _admin()
    try:
        with client:
            rows = (client.table("projects").delete().eq("id", str(project_id))
                .eq("user_id", user.id).execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="Project not found.")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not delete project.") from exc
