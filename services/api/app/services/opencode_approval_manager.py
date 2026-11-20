"""OpenCode permission polling and owner-scoped approval dispatch."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import httpx

from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore

_SESSION = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_PERMISSION = re.compile(r"^[A-Za-z0-9_-]{1,160}$")


class OpenCodeApprovalManager:
    def __init__(self, *, store: OpenCodeLifecycleStore, timeout: float = 10.0) -> None:
        self._store = store
        self._timeout = timeout

    @staticmethod
    def _gateway_url(base_url: str, gateway_path: str, route: str) -> str:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("opencode_gateway_origin_invalid")
        if gateway_path != gateway_path.rstrip("/") or not re.fullmatch(
            r"/v1/runtime-gateway/[0-9a-f-]{36}", gateway_path
        ):
            raise ValueError("opencode_gateway_path_invalid")
        if not route.startswith("/") or ".." in route.split("/"):
            raise ValueError("opencode_gateway_route_invalid")
        return base_url.rstrip("/") + gateway_path + route

    def collect_pending(
        self, *, user_id: str, run_id: str, session_id: str,
        base_url: str, gateway_path: str, runtime_token: str,
    ) -> list[dict]:
        if not _SESSION.fullmatch(session_id or ""):
            raise ValueError("opencode_session_id_invalid")
        url = self._gateway_url(
            base_url, gateway_path, f"/api/session/{session_id}/permission"
        )
        with httpx.Client(
            timeout=self._timeout, follow_redirects=False, trust_env=False,
            headers={"Authorization": f"Bearer {runtime_token}", "Accept": "application/json"},
        ) as client:
            response = client.get(url)
            if 300 <= response.status_code < 400 or response.status_code != 200:
                raise RuntimeError("opencode_permission_fetch_failed")
            if response.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
                raise RuntimeError("opencode_permission_invalid_content_type")
            if len(response.content) > 128 * 1024:
                raise RuntimeError("opencode_permission_response_too_large")
            payload = response.json()
        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list) or len(items) > 100:
            raise RuntimeError("opencode_permission_response_invalid")
        stored = []
        for item in items:
            if not isinstance(item, dict):
                continue
            permission_id = item.get("id")
            item_session = item.get("sessionID") or item.get("sessionId") or session_id
            permission_type = item.get("permission") or item.get("type") or "unknown"
            if not _PERMISSION.fullmatch(str(permission_id or "")) or item_session != session_id:
                continue
            resource = item.get("metadata") or item.get("patterns") or {}
            if isinstance(resource, list):
                resource = {"patterns": resource[:50]}
            if not isinstance(resource, dict):
                resource = {"description": str(resource)[:500]}
            stored.append(self._store.record_approval(
                user_id=user_id, run_id=run_id, session_id=session_id,
                permission_id=permission_id, permission_type=str(permission_type)[:80],
                resource=resource,
            ))
        return stored

    def decide(
        self, *, user_id: str, approval_id: str, decision: str,
        base_url: str, gateway_path: str, runtime_token: str,
    ) -> bool:
        def dispatch(session_id: str, permission_id: str, selected: str) -> None:
            if not _SESSION.fullmatch(session_id) or not _PERMISSION.fullmatch(permission_id):
                raise ValueError("opencode_permission_identity_invalid")
            url = self._gateway_url(
                base_url, gateway_path,
                f"/api/session/{session_id}/permission/{permission_id}/reply",
            )
            with httpx.Client(
                timeout=self._timeout, follow_redirects=False, trust_env=False,
                headers={"Authorization": f"Bearer {runtime_token}"},
            ) as client:
                response = client.post(url, json={"reply": selected})
                if 300 <= response.status_code < 400 or response.status_code not in {200, 204}:
                    raise RuntimeError("opencode_permission_reply_failed")

        return self._store.decide_approval(
            user_id=user_id, approval_id=approval_id, decision=decision,
            dispatch_upstream=dispatch,
        )
