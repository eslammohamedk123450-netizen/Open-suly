"""Owner-scoped, bounded project snapshot builder for isolated engine workspaces.

This reads SULY's canonical project_files rows; it never writes to a host path.
The provisioner must materialize the returned snapshot inside a fresh sandbox.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID, uuid4
from pathlib import PurePosixPath

from supabase import Client

_MAX_FILES = 200
_MAX_FILE_BYTES = 256 * 1024
_MAX_TOTAL_BYTES = 5 * 1024 * 1024
_BLOCKED = {".git", "node_modules", ".suly", "__pycache__", "secrets"}
_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")


class ProjectWorkspaceError(RuntimeError):
    pass


class ProjectWorkspaceStore:
    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    def _path(value: object) -> str:
        if not isinstance(value, str) or not value or len(value) > 240:
            raise ValueError("workspace_path_invalid")
        if "\x00" in value or "\\" in value or any(ord(c) < 32 for c in value):
            raise ValueError("workspace_path_invalid")
        parts = value.split("/")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in ("", ".", "..") for part in parts):
            raise ValueError("workspace_path_invalid")
        if any(part.lower() in _BLOCKED or part.lower().startswith(".env") for part in parts):
            raise ValueError("workspace_path_reserved")
        return value

    def snapshot(self, *, user_id: str, project_id: str) -> dict[str, Any]:
        try:
            if str(UUID(user_id)) != user_id or str(UUID(project_id)) != project_id:
                raise ValueError
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("workspace_identity_invalid") from exc

        project = (
            self._client.table("projects").select("id")
            .eq("id", project_id).eq("user_id", user_id).limit(1).execute().data
        )
        if not project:
            raise ProjectWorkspaceError("project_not_found")

        rows = (
            self._client.table("project_files")
            .select("path,content,size_bytes,updated_at")
            .eq("project_id", project_id).eq("user_id", user_id)
            .order("path").limit(_MAX_FILES + 1).execute().data
        ) or []
        if len(rows) > _MAX_FILES:
            raise ProjectWorkspaceError("workspace_file_limit_exceeded")

        files: list[dict[str, Any]] = []
        total = 0
        for row in rows:
            path = self._path(row.get("path"))
            content = row.get("content")
            if not isinstance(content, str) or "\x00" in content:
                raise ProjectWorkspaceError("workspace_binary_or_invalid_file")
            encoded = content.encode("utf-8")
            size = len(encoded)
            if size > _MAX_FILE_BYTES:
                raise ProjectWorkspaceError("workspace_file_too_large")
            total += size
            if total > _MAX_TOTAL_BYTES:
                raise ProjectWorkspaceError("workspace_snapshot_too_large")
            files.append({
                "path": path,
                "content": content,
                "size_bytes": size,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "updated_at": row.get("updated_at"),
            })

        # Deterministic revision excludes timestamps and is stable for identical content.
        digest = hashlib.sha256()
        for item in files:
            digest.update(item["path"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(item["sha256"].encode("ascii"))
            digest.update(b"\n")
        return {
            "workspace_id": str(uuid4()),
            "project_id": project_id,
            "revision": digest.hexdigest(),
            "file_count": len(files),
            "total_bytes": total,
            "files": files,
        }
