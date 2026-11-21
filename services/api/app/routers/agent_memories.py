"""User-owned, explicitly managed SULY agent memory API.

Memory is written only through authenticated user actions. Engines receive a
bounded read-only projection and never receive direct database credentials.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.project_workspace_store import contains_secret_material

router = APIRouter(prefix="/v1/memories", tags=["agent memory"])
_TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_SELECT = "id,memory_key,content,tags,status,created_at,updated_at"


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_key: StrictStr = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    content: StrictStr = Field(min_length=1, max_length=2000)
    tags: list[StrictStr] = Field(default_factory=list, max_length=8)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("memory_content_required")
        if contains_secret_material(value):
            raise ValueError("memory_must_not_contain_secret_material")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not _TAG.fullmatch(tag) for tag in value):
            raise ValueError("memory_tags_invalid")
        return value


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: StrictStr | None = Field(default=None, min_length=1, max_length=2000)
    tags: list[StrictStr] | None = Field(default=None, max_length=8)
    status: str | None = Field(default=None, pattern=r"^(active|archived)$")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("memory_content_required")
        if contains_secret_material(value):
            raise ValueError("memory_must_not_contain_secret_material")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if len(value) != len(set(value)) or any(not _TAG.fullmatch(tag) for tag in value):
            raise ValueError("memory_tags_invalid")
        return value


def _client():
    if not get_settings().agent_memory_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SULY agent memory is not enabled on this server.",
        )
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Memory storage is not configured.")
    return client


def _memory_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail="Memory note not found.") from exc
    if str(parsed) != value:
        raise HTTPException(status_code=404, detail="Memory note not found.")
    return value


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    if isinstance(data, dict):
        return [data]
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


@router.get("")
def list_memories(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    try:
        response = (
            _client().table("agent_memories")
            .select(_SELECT)
            .eq("user_id", user.id)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        return {"items": _rows(response)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load SULY memory.") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_memory(
    request: MemoryCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    payload = {
        "user_id": user.id,
        "memory_key": request.memory_key,
        "content": request.content,
        "tags": request.tags,
        "status": "active",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = (
            _client().table("agent_memories")
            .insert(payload)
            .select(_SELECT)
            .execute()
        )
        rows = _rows(response)
        if not rows:
            raise RuntimeError("memory_insert_returned_no_row")
        return {"item": rows[0]}
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code == "23505" or "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A memory note with this key already exists.") from exc
        raise HTTPException(status_code=503, detail="Could not save SULY memory.") from exc


@router.patch("/{memory_id}")
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    memory_id = _memory_id(memory_id)
    payload = {
        key: value for key, value in request.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if not payload:
        raise HTTPException(status_code=422, detail="At least one memory field must be provided.")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        response = (
            _client().table("agent_memories")
            .update(payload)
            .eq("id", memory_id)
            .eq("user_id", user.id)
            .select(_SELECT)
            .execute()
        )
        rows = _rows(response)
        if not rows:
            raise HTTPException(status_code=404, detail="Memory note not found.")
        return {"item": rows[0]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not update SULY memory.") from exc


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, bool]:
    memory_id = _memory_id(memory_id)
    try:
        response = (
            _client().table("agent_memories")
            .delete()
            .eq("id", memory_id)
            .eq("user_id", user.id)
            .select("id")
            .execute()
        )
        deleted = bool(_rows(response))
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory note not found.")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not delete SULY memory.") from exc
