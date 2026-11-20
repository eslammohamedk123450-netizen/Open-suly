"""Owner-scoped text file API for project workspaces."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase_admin_client

router = APIRouter(prefix="/v1/projects", tags=["project-files"])

MAX_FILE_BYTES = 256 * 1024
MAX_PROJECT_FILES = 200
MAX_REVISIONS = 50
BLOCKED_PARTS = {"..", ".git", "node_modules", ".suly"}


class SaveProjectFileRequest(BaseModel):
    content: str = Field(max_length=MAX_FILE_BYTES)


def _admin():
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Project file service is not configured.")
    return client


def _safe_path(value: str) -> str:
    if not value or len(value) > 512 or "\x00" in value or "\\" in value:
        raise HTTPException(status_code=422, detail="Invalid project file path.")
    path = PurePosixPath(value)
    parts = value.split("/")
    if path.is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise HTTPException(status_code=422, detail="Invalid project file path.")
    if any(part.lower() in BLOCKED_PARTS or part.lower().startswith(".env") for part in parts):
        raise HTTPException(status_code=422, detail="This project file path is reserved.")
    if any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=422, detail="Invalid project file path.")
    return value


def _owned_project(client: Any, project_id: UUID, user_id: str) -> dict[str, Any]:
    rows = (client.table("projects").select("id")
        .eq("id", str(project_id)).eq("user_id", user_id).limit(1).execute().data)
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found.")
    return rows[0]


@router.get("/{project_id}/files")
def list_project_files(
    project_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            rows = (client.table("project_files")
                .select("id,path,size_bytes,updated_at")
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .order("path").limit(MAX_PROJECT_FILES).execute().data)
        return {"items": [
            {"id": row["id"], "path": row["path"],
             "size": row["size_bytes"], "updated_at": row["updated_at"]}
            for row in (rows or [])
        ]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not list project files.") from exc


@router.get("/{project_id}/file")
def read_project_file(
    project_id: UUID,
    path: str = Query(min_length=1, max_length=512),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    safe_path = _safe_path(path)
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            rows = (client.table("project_files").select("id,path,content,updated_at")
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .eq("path", safe_path).limit(1).execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="Project file not found.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read project file.") from exc


@router.get("/{project_id}/file/history")
def list_project_file_history(
    project_id: UUID,
    path: str = Query(min_length=1, max_length=512),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    safe_path = _safe_path(path)
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            files = (client.table("project_files").select("id")
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .eq("path", safe_path).limit(1).execute().data)
            if not files:
                raise HTTPException(status_code=404, detail="Project file not found.")
            rows = (client.table("project_file_revisions")
                .select("id,path,size_bytes,created_at")
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .eq("file_id", files[0]["id"])
                .order("created_at", desc=True).limit(MAX_REVISIONS).execute().data)
        return {"items": rows or []}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not load file history.") from exc


@router.get("/{project_id}/file/history/{revision_id}")
def read_project_file_revision(
    project_id: UUID,
    revision_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            rows = (client.table("project_file_revisions")
                .select("id,path,content,size_bytes,created_at")
                .eq("id", str(revision_id)).eq("project_id", str(project_id))
                .eq("user_id", user.id).limit(1).execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="File revision not found.")
        return rows[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read file revision.") from exc


@router.post("/{project_id}/file/history/{revision_id}/restore")
def restore_project_file_revision(
    project_id: UUID,
    revision_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            rows = (client.table("project_file_revisions")
                .select("id,file_id,path,content,size_bytes")
                .eq("id", str(revision_id)).eq("project_id", str(project_id))
                .eq("user_id", user.id).limit(1).execute().data)
            if not rows:
                raise HTTPException(status_code=404, detail="File revision not found.")
            revision = rows[0]
            restored = (client.table("project_files").update({
                "content": revision["content"],
                "size_bytes": revision["size_bytes"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", revision["file_id"])
              .eq("project_id", str(project_id)).eq("user_id", user.id)
              .execute().data)
        if not restored:
            raise HTTPException(status_code=404, detail="Project file no longer exists.")
        row = restored[0]
        return {"restored": True, "path": row["path"], "updated_at": row["updated_at"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not restore file revision.") from exc


@router.put("/{project_id}/file")
def save_project_file(
    project_id: UUID,
    request: SaveProjectFileRequest,
    path: str = Query(min_length=1, max_length=512),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    safe_path = _safe_path(path)
    if "\x00" in request.content:
        raise HTTPException(status_code=422, detail="Binary content is not supported.")
    size_bytes = len(request.content.encode("utf-8"))
    if size_bytes > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Project files are limited to 256 KiB.")
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            existing = (client.table("project_files").select("id")
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .eq("path", safe_path).limit(1).execute().data)
            if not existing:
                count = (client.table("project_files").select("id")
                    .eq("project_id", str(project_id)).eq("user_id", user.id)
                    .limit(MAX_PROJECT_FILES).execute().data)
                if len(count or []) >= MAX_PROJECT_FILES:
                    raise HTTPException(status_code=409, detail="This project has reached the 200-file limit.")
            rows = (client.table("project_files").upsert({
                "project_id": str(project_id), "user_id": user.id,
                "path": safe_path, "content": request.content,
                "size_bytes": size_bytes,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="project_id,path").execute().data)
        if not rows:
            raise HTTPException(status_code=503, detail="Project file was not saved.")
        row = rows[0]
        return {"id": row["id"], "path": row["path"], "size": size_bytes,
                "updated_at": row["updated_at"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not save project file.") from exc


@router.delete("/{project_id}/file")
def delete_project_file(
    project_id: UUID,
    path: str = Query(min_length=1, max_length=512),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, bool]:
    safe_path = _safe_path(path)
    client = _admin()
    try:
        with client:
            _owned_project(client, project_id, user.id)
            rows = (client.table("project_files").delete()
                .eq("project_id", str(project_id)).eq("user_id", user.id)
                .eq("path", safe_path).execute().data)
        if not rows:
            raise HTTPException(status_code=404, detail="Project file not found.")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not delete project file.") from exc
