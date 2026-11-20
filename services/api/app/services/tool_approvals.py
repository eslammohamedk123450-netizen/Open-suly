"""Server-only persistence boundary for user-approved tool scopes."""
from __future__ import annotations

from typing import Any

from supabase import Client


class ToolApprovalStore:
    """Uses only the server admin client; never accept an actor ID from request data."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def active_scopes(self, user_id: str) -> frozenset[str]:
        rows = (
            self._client.table("tool_approvals")
            .select("permission_scope")
            .eq("user_id", user_id)
            .is_("revoked_at", "null")
            .limit(200)
            .execute()
            .data
        )
        return frozenset(
            row["permission_scope"] for row in (rows or [])
            if isinstance(row, dict) and isinstance(row.get("permission_scope"), str)
        )

    def grant(self, user_id: str, permission_scope: str) -> str:
        result = self._client.rpc(
            "grant_tool_approval",
            {
                "p_user_id": user_id,
                "p_permission_scope": permission_scope,
                "p_actor_user_id": user_id,
            },
        ).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        if not isinstance(result, str):
            raise RuntimeError("tool_approval_grant_failed")
        return result

    def revoke(self, user_id: str, permission_scope: str) -> bool:
        result = self._client.rpc(
            "revoke_tool_approval",
            {
                "p_user_id": user_id,
                "p_permission_scope": permission_scope,
                "p_actor_user_id": user_id,
            },
        ).execute().data
        if isinstance(result, list):
            result = result[0] if result else 0
        return bool(result)

    def list_approvals(self, user_id: str) -> list[dict[str, Any]]:
        rows = (
            self._client.table("tool_approvals")
            .select("id,permission_scope,granted_at,revoked_at")
            .eq("user_id", user_id)
            .order("granted_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        return rows or []

    def list_events(self, user_id: str) -> list[dict[str, Any]]:
        rows = (
            self._client.table("tool_approval_events")
            .select("id,approval_id,permission_scope,event_type,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
            .data
        )
        return rows or []
