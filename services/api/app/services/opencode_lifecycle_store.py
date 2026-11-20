"""Durable owner-scoped OpenCode lifecycle persistence.

Only the trusted API worker should construct this service with a server-side
Supabase client. Never return credentials or raw tool output to end users.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable
from uuid import UUID

from supabase import Client

_EVENT_TYPES = frozenset({
    "task.started", "task.status", "task.completed", "task.failed",
    "task.cancelled", "permission.requested", "permission.decided",
    "changes.collected", "changes.approved", "changes.rejected",
})
_STATUSES = frozenset({
    "queued", "provisioning", "running", "waiting_approval", "collecting",
    "review_ready", "applying", "completed", "failed", "cancelled", "expired",
})
_SESSION = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_PERMISSION = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MAX_EVENT_BYTES = 16_384
_MAX_CHANGESET_BYTES = 2 * 1024 * 1024


def _uuid(value: str, code: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(code) from exc
    if str(parsed) != value:
        raise ValueError(code)
    return value


def _safe_json(value: Any, *, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("opencode_payload_invalid")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > limit:
        raise ValueError("opencode_payload_too_large")
    # Secrets and raw execution output must never be persisted in the event feed.
    forbidden = {"access_token", "authorization", "password", "secret", "api_key", "prompt", "tool_output"}
    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in forbidden:
                    raise ValueError("opencode_sensitive_event_field")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return value


class OpenCodeLifecycleStore:
    """Persists task state, sanitized events, approvals and reviewable changes."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def create_run(
        self, *, user_id: str, project_id: str, task_id: str, engine_run_id: str,
        workspace_revision: str,
    ) -> dict[str, Any]:
        for value in (user_id, project_id, task_id, engine_run_id):
            _uuid(value, "opencode_task_identity_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", workspace_revision or ""):
            raise ValueError("opencode_workspace_revision_invalid")
        row = self._client.table("opencode_task_runs").insert({
            "user_id": user_id, "project_id": project_id, "task_id": task_id,
            "engine_run_id": engine_run_id, "workspace_revision": workspace_revision,
            "status": "queued",
        }).execute().data
        if not row:
            raise RuntimeError("opencode_task_run_persistence_failed")
        return self._run_projection(row[0])

    def set_runtime(
        self, *, user_id: str, run_id: str, runtime_id: str,
        session_id: str, status: str = "running",
    ) -> bool:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if not isinstance(runtime_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", runtime_id):
            raise ValueError("opencode_runtime_id_invalid")
        if not isinstance(session_id, str) or not _SESSION.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        if status not in _STATUSES:
            raise ValueError("opencode_task_status_invalid")
        rows = self._client.table("opencode_task_runs").update({
            "runtime_id": runtime_id, "upstream_session_id": session_id, "status": status,
        }).eq("id", run_id).eq("user_id", user_id).execute().data
        return bool(rows)

    def update_status(self, *, user_id: str, run_id: str, status: str, error_code: str | None = None) -> bool:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if status not in _STATUSES:
            raise ValueError("opencode_task_status_invalid")
        if error_code is not None and (not re.fullmatch(r"[a-z0-9_]{1,80}", error_code)):
            raise ValueError("opencode_error_code_invalid")
        payload: dict[str, Any] = {"status": status, "error_code": error_code}
        if status in {"running", "provisioning"}:
            payload["started_at"] = "now()"
        if status in {"completed", "failed", "cancelled", "expired"}:
            payload["finished_at"] = "now()"
        rows = self._client.table("opencode_task_runs").update(payload).eq(
            "id", run_id
        ).eq("user_id", user_id).execute().data
        return bool(rows)

    def append_event(
        self, *, user_id: str, run_id: str, sequence: int, event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("opencode_event_sequence_invalid")
        if event_type not in _EVENT_TYPES:
            raise ValueError("opencode_event_type_invalid")
        safe_payload = _safe_json(payload, limit=_MAX_EVENT_BYTES)
        rows = self._client.table("opencode_task_events").upsert({
            "run_id": run_id, "user_id": user_id, "sequence": sequence,
            "event_type": event_type, "payload": safe_payload,
        }, on_conflict="run_id,sequence", ignore_duplicates=True).execute().data
        # Duplicate sequence numbers are idempotent; callers may safely retry.
        return bool(rows) or True

    def record_approval(
        self, *, user_id: str, run_id: str, session_id: str,
        permission_id: str, permission_type: str, resource: dict[str, Any],
    ) -> dict[str, Any]:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if not _SESSION.fullmatch(session_id or "") or not _PERMISSION.fullmatch(permission_id or ""):
            raise ValueError("opencode_permission_identity_invalid")
        if not isinstance(permission_type, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", permission_type):
            raise ValueError("opencode_permission_type_invalid")
        safe_resource = _safe_json(resource, limit=8192)
        rows = self._client.table("opencode_approvals").upsert({
            "run_id": run_id, "user_id": user_id,
            "upstream_permission_id": permission_id, "session_id": session_id,
            "permission_type": permission_type, "resource": safe_resource,
        }, on_conflict="run_id,upstream_permission_id").execute().data
        if not rows:
            raise RuntimeError("opencode_approval_persistence_failed")
        return self._approval_projection(rows[0])

    def list_pending_approvals(self, *, user_id: str, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("opencode_approval_limit_invalid")
        rows = self._client.table("opencode_approvals").select(
            "id,run_id,session_id,upstream_permission_id,permission_type,resource,status,created_at"
        ).eq("user_id", user_id).eq("run_id", run_id).eq("status", "pending").order(
            "created_at"
        ).limit(limit).execute().data or []
        return [self._approval_projection(row) for row in rows]

    def decide_approval(
        self, *, user_id: str, approval_id: str, decision: str,
        dispatch_upstream: Callable[[str, str, str], None],
    ) -> bool:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(approval_id, "opencode_approval_identity_invalid")
        if decision not in {"once", "always", "reject"}:
            raise ValueError("opencode_approval_decision_invalid")
        row = self._client.table("opencode_approvals").select(
            "id,run_id,session_id,upstream_permission_id,status"
        ).eq("id", approval_id).eq("user_id", user_id).eq("status", "pending").limit(1).execute().data
        if not row:
            return False
        item = row[0]
        # Dispatch only after owner and pending-state checks; upstream must enforce
        # its own permission ID/session scope. The DB transition below is conditional.
        dispatch_upstream(item["session_id"], item["upstream_permission_id"], decision)
        status = {"once": "approved_once", "always": "approved_always", "reject": "rejected"}[decision]
        updated = self._client.table("opencode_approvals").update({
            "status": status, "decided_at": "now()",
        }).eq("id", approval_id).eq("user_id", user_id).eq("status", "pending").execute().data
        return bool(updated)

    def create_change_set(
        self, *, user_id: str, project_id: str, run_id: str,
        base_revision: str, changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        _uuid(user_id, "opencode_task_identity_invalid")
        _uuid(project_id, "opencode_task_identity_invalid")
        _uuid(run_id, "opencode_task_identity_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", base_revision or ""):
            raise ValueError("opencode_base_revision_invalid")
        if not isinstance(changes, list) or len(changes) > 500:
            raise ValueError("opencode_changes_invalid")
        encoded = json.dumps(changes, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        if len(encoded) > _MAX_CHANGESET_BYTES:
            raise ValueError("opencode_changes_too_large")
        for change in changes:
            if not isinstance(change, dict) or change.get("action") not in {"create", "update", "delete"}:
                raise ValueError("opencode_change_invalid")
            if not isinstance(change.get("path"), str) or not change["path"] or len(change["path"]) > 512:
                raise ValueError("opencode_change_path_invalid")
            if change["action"] in {"create", "update"}:
                content = change.get("content")
                if not isinstance(content, str) or len(content.encode("utf-8")) > 1024 * 1024:
                    raise ValueError("opencode_change_content_invalid")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                if change.get("sha256") != digest:
                    raise ValueError("opencode_change_digest_mismatch")
        rows = self._client.table("opencode_change_sets").insert({
            "run_id": run_id, "user_id": user_id, "project_id": project_id,
            "base_revision": base_revision, "changes": changes, "status": "review_ready",
        }).execute().data
        if not rows:
            raise RuntimeError("opencode_changeset_persistence_failed")
        return self._changeset_projection(rows[0])

    @staticmethod
    def _run_projection(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "project_id", "task_id", "engine_run_id", "runtime_id",
                "upstream_session_id", "status", "workspace_revision", "error_code",
                "started_at", "finished_at", "created_at", "updated_at")
        return {key: row.get(key) for key in keys}

    @staticmethod
    def _approval_projection(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "run_id", "session_id", "upstream_permission_id",
                "permission_type", "resource", "status", "created_at")
        return {key: row.get(key) for key in keys}

    @staticmethod
    def _changeset_projection(row: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "run_id", "project_id", "base_revision", "status", "changes", "created_at")
        return {key: row.get(key) for key in keys}
