"""SULY-owned Hermes session and memory persistence.

Construct this store only with a server-side Supabase client. Hermes never
receives database credentials and cannot write memory directly. The caller
chooses the scope and passes only the bounded context returned here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from supabase import Client

_MAX_MEMORY_BYTES = 32 * 1024
_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_MEMORY_ITEMS = 100


def _uuid(value: str, code: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(code) from exc
    if str(parsed) != value:
        raise ValueError(code)
    return value


def _json_value(value: Any, *, max_bytes: int = _MAX_MEMORY_BYTES) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("hermes_memory_value_invalid") from exc
    if not encoded or len(encoded) > max_bytes:
        raise ValueError("hermes_memory_value_too_large")
    return value


class HermesStateStore:
    """Persists Hermes session mappings and SULY-authoritative scoped memory."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def register_session(
        self, *, user_id: str, engine_session_id: str,
        project_id: str | None = None, conversation_id: str | None = None,
        task_id: str | None = None, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owner = _uuid(user_id, "hermes_session_owner_invalid")
        for value, code in (
            (project_id, "hermes_session_project_invalid"),
            (conversation_id, "hermes_session_conversation_invalid"),
            (task_id, "hermes_session_task_invalid"),
        ):
            if value is not None:
                _uuid(value, code)
        if not isinstance(engine_session_id, str) or not 1 <= len(engine_session_id) <= 180:
            raise ValueError("hermes_engine_session_id_invalid")
        safe_metadata = _json_value(metadata or {}, max_bytes=8192)
        row = self._client.table("hermes_sessions").insert({
            "user_id": owner, "engine_session_id": engine_session_id,
            "project_id": project_id, "conversation_id": conversation_id,
            "task_id": task_id, "metadata": safe_metadata, "status": "active",
        }).execute().data
        if not row or not isinstance(row[0], dict):
            raise RuntimeError("hermes_session_persistence_failed")
        return self._session_projection(row[0])

    def set_session_status(self, *, user_id: str, session_id: str, status: str) -> bool:
        owner = _uuid(user_id, "hermes_session_owner_invalid")
        session = _uuid(session_id, "hermes_session_id_invalid")
        if status not in {"active", "paused", "completed", "failed", "expired"}:
            raise ValueError("hermes_session_status_invalid")
        rows = self._client.table("hermes_sessions").update({
            "status": status, "updated_at": datetime.now(timezone.utc).isoformat(), "last_activity_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", session).eq("user_id", owner).execute().data
        return bool(rows)

    def put_memory(
        self, *, user_id: str, memory_key: str, content: Any,
        scope: str = "user", project_id: str | None = None,
        conversation_id: str | None = None, source: str = "suly",
    ) -> dict[str, Any]:
        owner = _uuid(user_id, "hermes_memory_owner_invalid")
        if not isinstance(memory_key, str) or not 1 <= len(memory_key.strip()) <= 160:
            raise ValueError("hermes_memory_key_invalid")
        if scope not in {"user", "project", "conversation"}:
            raise ValueError("hermes_memory_scope_invalid")
        if scope == "user" and (project_id is not None or conversation_id is not None):
            raise ValueError("hermes_memory_scope_target_invalid")
        if scope == "project" and (project_id is None or conversation_id is not None):
            raise ValueError("hermes_memory_scope_target_invalid")
        if scope == "conversation" and conversation_id is None:
            raise ValueError("hermes_memory_scope_target_invalid")
        if project_id is not None:
            _uuid(project_id, "hermes_memory_project_invalid")
        if conversation_id is not None:
            _uuid(conversation_id, "hermes_memory_conversation_invalid")
        if source not in {"suly", "user_approved_import", "agent_proposal"}:
            raise ValueError("hermes_memory_source_invalid")
        safe_content = _json_value(content)
        rows = self._client.table("hermes_memory_entries").upsert({
            "user_id": owner, "scope": scope, "project_id": project_id,
            "conversation_id": conversation_id, "memory_key": memory_key.strip(),
            "content": safe_content, "source": source, "status": "active",
        }, on_conflict="user_id,scope,memory_key,project_id,conversation_id").execute().data
        if not rows or not isinstance(rows[0], dict):
            raise RuntimeError("hermes_memory_persistence_failed")
        return self._memory_projection(rows[0])

    def list_memory(
        self, *, user_id: str, scope: str = "user",
        project_id: str | None = None, conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        owner = _uuid(user_id, "hermes_memory_owner_invalid")
        if scope not in {"user", "project", "conversation"}:
            raise ValueError("hermes_memory_scope_invalid")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_MEMORY_ITEMS:
            raise ValueError("hermes_memory_limit_invalid")
        query = self._client.table("hermes_memory_entries").select(
            "id,user_id,scope,project_id,conversation_id,memory_key,content,source,status,revision,updated_at"
        ).eq("user_id", owner).eq("scope", scope).eq("status", "active")
        if scope == "user":
            query = query.is_("project_id", "null").is_("conversation_id", "null")
        elif scope == "project":
            query = query.eq("project_id", _uuid(project_id or "", "hermes_memory_project_invalid")).is_("conversation_id", "null")
        else:
            query = query.eq("conversation_id", _uuid(conversation_id or "", "hermes_memory_conversation_invalid"))
        rows = query.order("updated_at", desc=True).limit(limit).execute().data or []
        return [self._memory_projection(row) for row in rows if isinstance(row, dict)]

    def context_for_task(
        self, *, user_id: str, project_id: str | None = None,
        conversation_id: str | None = None, max_bytes: int = _MAX_CONTEXT_BYTES,
    ) -> list[dict[str, Any]]:
        """Return bounded context in explicit precedence order; never cross owners."""
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1024 <= max_bytes <= _MAX_CONTEXT_BYTES:
            raise ValueError("hermes_memory_context_limit_invalid")
        entries = self.list_memory(user_id=user_id, scope="user", limit=50)
        if project_id is not None:
            entries += self.list_memory(user_id=user_id, scope="project", project_id=project_id, limit=50)
        if conversation_id is not None:
            entries += self.list_memory(user_id=user_id, scope="conversation", conversation_id=conversation_id, limit=50)
        result: list[dict[str, Any]] = []
        used = 2
        for entry in entries:
            encoded = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if used + len(encoded) + 1 > max_bytes:
                break
            result.append(entry)
            used += len(encoded) + 1
        return result

    @staticmethod
    def _session_projection(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "user_id", "project_id", "conversation_id", "task_id",
                "engine_session_id", "status", "context_revision", "created_at",
                "updated_at", "last_activity_at")
        return {key: row.get(key) for key in keys}

    @staticmethod
    def _memory_projection(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "scope", "project_id", "conversation_id", "memory_key",
                "content", "source", "status", "revision", "updated_at")
        return {key: row.get(key) for key in keys}
