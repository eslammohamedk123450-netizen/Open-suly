"""Server-only persistence for owner-scoped OpenCode session mappings.

The upstream session is created only after a task-scoped runtime lease exists.
This store records the mapping; it does not provision containers or grant access.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from supabase import Client

_SESSION_ID = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_TITLE_MAX = 120
_STATUSES = frozenset({"active", "paused", "completed", "failed", "expired"})


class OpenCodeSessionStore:
    def __init__(self, client: Client) -> None:
        self._client = client

    def register(
        self,
        *,
        user_id: str,
        project_id: str,
        upstream_session_id: str,
        title: str,
        task_id: str | None = None,
        engine_run_id: str | None = None,
        workspace_revision: str | None = None,
    ) -> dict[str, Any]:
        """Persist a session only when project/task/run ownership matches in SQL."""
        try:
            owner = UUID(user_id)
            project = UUID(project_id)
            task = UUID(task_id) if task_id is not None else None
            run = UUID(engine_run_id) if engine_run_id is not None else None
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("opencode_session_identity_invalid") from exc
        if str(owner) != user_id or str(project) != project_id:
            raise ValueError("opencode_session_identity_invalid")
        if (task is None) != (run is None):
            raise ValueError("opencode_session_task_run_pair_required")
        if task_id is not None and (str(task) != task_id or str(run) != engine_run_id):
            raise ValueError("opencode_session_identity_invalid")
        if not isinstance(upstream_session_id, str) or not _SESSION_ID.fullmatch(upstream_session_id):
            raise ValueError("opencode_upstream_session_id_invalid")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > _TITLE_MAX:
            raise ValueError("opencode_session_title_invalid")
        if workspace_revision is not None and (
            not isinstance(workspace_revision, str) or len(workspace_revision) > 128
        ):
            raise ValueError("opencode_workspace_revision_invalid")

        payload = {
            "user_id": user_id,
            "project_id": project_id,
            "task_id": task_id,
            "engine_run_id": engine_run_id,
            "upstream_session_id": upstream_session_id,
            "title": title.strip(),
            "workspace_revision": workspace_revision,
            "status": "active",
        }
        rows = self._client.table("opencode_sessions").insert(payload).execute().data
        if not rows or not isinstance(rows[0], dict):
            raise RuntimeError("opencode_session_persistence_failed")
        return self._public_row(rows[0])

    def list_project(
        self, *, user_id: str, project_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        try:
            UUID(user_id)
            UUID(project_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("opencode_session_identity_invalid") from exc
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("opencode_session_limit_invalid")
        rows = (
            self._client.table("opencode_sessions")
            .select("id,user_id,project_id,task_id,engine_run_id,upstream_session_id,title,status,workspace_revision,created_at,updated_at,last_activity_at")
            .eq("user_id", user_id)
            .eq("project_id", project_id)
            .order("last_activity_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return [self._public_row(row) for row in (rows or []) if isinstance(row, dict)]

    def update_status(
        self, *, user_id: str, session_record_id: str, status: str
    ) -> bool:
        if status not in _STATUSES:
            raise ValueError("opencode_session_status_invalid")
        try:
            UUID(user_id)
            UUID(session_record_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("opencode_session_identity_invalid") from exc
        rows = (
            self._client.table("opencode_sessions")
            .update({"status": status})
            .eq("id", session_record_id)
            .eq("user_id", user_id)
            .execute()
            .data
        )
        return bool(rows)

    @staticmethod
    def _public_row(row: dict[str, Any]) -> dict[str, Any]:
        # Explicit projection: never return access tokens, runtime URLs, or secrets.
        allowed = (
            "id", "project_id", "task_id", "engine_run_id",
            "upstream_session_id", "title", "status", "workspace_revision",
            "created_at", "updated_at", "last_activity_at",
        )
        return {key: row.get(key) for key in allowed}
