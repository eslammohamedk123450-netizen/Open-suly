"""Fail-closed Hermes tool gateway governed by SULY's persisted approvals.

This module is the only supported bridge for invoking Hermes tools. It does
not expose raw Supabase credentials or grant blanket shell/browser/MCP access.
The caller must provide a per-tool executor and a bounded task identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable
from uuid import UUID

from supabase import Client

_TOOL_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_MAX_ARGUMENT_BYTES = 16 * 1024
_BLOCKED_TOOLS = frozenset({
    "shell", "terminal", "computer", "browser", "mcp", "filesystem.write",
    "process.exec", "docker", "secrets.read",
})


def _owner(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("hermes_tool_owner_invalid") from exc
    if str(parsed) != value:
        raise ValueError("hermes_tool_owner_invalid")
    return value


class HermesToolGateway:
    """Check exact owner + exact engine/tool scope before dispatching a tool."""

    def __init__(self, client: Client) -> None:
        self._client = client

    @staticmethod
    def permission_scope(tool_id: str) -> str:
        if not isinstance(tool_id, str) or not _TOOL_ID.fullmatch(tool_id):
            raise ValueError("hermes_tool_id_invalid")
        return f"engine:hermes-agent:tool:{tool_id}"

    def is_approved(self, *, user_id: str, tool_id: str) -> bool:
        owner = _owner(user_id)
        scope = self.permission_scope(tool_id)
        rows = self._client.table("tool_approvals").select("id").eq(
            "user_id", owner
        ).eq("permission_scope", scope).is_("revoked_at", "null").limit(1).execute().data
        return bool(rows)

    def invoke(
        self, *, user_id: str, task_id: str, tool_id: str,
        arguments: dict[str, Any], executor: Callable[[dict[str, Any]], Any],
    ) -> Any:
        owner = _owner(user_id)
        _owner(task_id)
        if tool_id in _BLOCKED_TOOLS:
            raise PermissionError("hermes_tool_requires_dedicated_sandbox_bridge")
        scope = self.permission_scope(tool_id)
        if not callable(executor):
            raise ValueError("hermes_tool_executor_invalid")
        try:
            encoded = json.dumps(
                arguments, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("hermes_tool_arguments_invalid") from exc
        if len(encoded) > _MAX_ARGUMENT_BYTES:
            raise ValueError("hermes_tool_arguments_too_large")

        # Recheck immediately before dispatch. Never trust an approval cached
        # in a Hermes session or passed back by the upstream engine.
        rows = self._client.table("tool_approvals").select("id").eq(
            "user_id", owner
        ).eq("permission_scope", scope).is_("revoked_at", "null").limit(1).execute().data
        if not rows:
            raise PermissionError("hermes_tool_approval_required")

        # Persist a metadata-only audit event. Arguments and tool output are
        # deliberately excluded; the hash is useful for incident correlation.
        self._client.table("tool_approval_events").insert({
            "user_id": owner,
            "approval_id": rows[0]["id"],
            "permission_scope": scope,
            "event_type": "tool_invocation_authorized",
            "actor_user_id": owner,
            "metadata": {
                "action": "tool_invocation_authorized",
                "engine_id": "hermes-agent",
                "tool_id": tool_id,
                "task_id": task_id,
                "arguments_sha256": hashlib.sha256(encoded).hexdigest(),
            },
        }).execute()
        return executor(arguments)
