"""Task-scoped, fail-closed HTTP client for the pinned OpenCode server.

This is a transport adapter only: it never provisions a runtime, accepts a client
URL, forwards local file paths, or enables shell/PTY/MCP/plugin capabilities.
Callers must obtain and validate a RuntimeLease before constructing it.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.services.runtime_broker_contract import RuntimeLease
from app.services import opencode_contract

_SESSION_ID = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_PERMISSION_ID = re.compile(r"^per[A-Za-z0-9_-]{1,128}$")
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_PROMPT_CHARS = 32_000
_ALLOWED_ROUTES = frozenset({
    ("GET", "/api/info"),
    ("POST", "/api/session"),
    ("GET", "/api/skill"),
    ("GET", "/api/provider"),
})


class OpenCodeTransportError(RuntimeError):
    """Sanitized upstream transport failure; never includes credentials/body."""


class OpenCodeHTTPClient:
    """Minimal HTTP surface for one validated task-attempt runtime lease."""

    def __init__(
        self,
        lease: RuntimeLease,
        *,
        task_id: str,
        engine_run_id: str,
        allowed_origins: frozenset[str],
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        lease.validate(
            task_id=task_id,
            engine_run_id=engine_run_id,
            engine_id="opencode",
            allowed_origins=allowed_origins,
        )
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("opencode_timeout_invalid")
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("opencode_timeout_invalid")
        self._lease = lease
        self._client = httpx.AsyncClient(
            base_url=lease.base_url,
            auth=("opencode", lease.access_token),
            headers={"Accept": "application/json", "User-Agent": "SULY-OpenCode-Bridge/1.0"},
            timeout=httpx.Timeout(float(timeout_seconds), connect=min(float(timeout_seconds), 5.0)),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            follow_redirects=False,
            verify=True,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> "OpenCodeHTTPClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> Any:
        fixed_route = (method, path) in _ALLOWED_ROUTES
        permission_list = method == "GET" and re.fullmatch(
            r"/api/session/(ses[A-Za-z0-9_-]{1,128})/permission", path
        )
        if not (fixed_route or permission_list):
            raise ValueError("opencode_route_not_allowed")
        try:
            async with self._client.stream(method, path, json=body) as response:
                if 300 <= response.status_code < 400:
                    raise OpenCodeTransportError("opencode_redirect_rejected")
                if response.status_code < 200 or response.status_code >= 300:
                    raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise OpenCodeTransportError("opencode_invalid_content_type")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise OpenCodeTransportError("opencode_response_too_large")
                    chunks.append(chunk)
        except OpenCodeTransportError:
            raise
        except httpx.HTTPError as exc:
            # Deliberately omit URL, request headers, response body and exception text.
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc
        try:
            return json.loads(b"".join(chunks))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise OpenCodeTransportError("opencode_invalid_json") from exc

    async def health(self) -> dict[str, Any]:
        result = await self._request_json("GET", "/api/info")
        if not isinstance(result, dict) or not isinstance(result.get("version"), str):
            raise OpenCodeTransportError("opencode_invalid_info_response")
        # Do not expose upstream hostnames, URLs, process IDs, or filesystem paths.
        return {"version": result["version"][:64]}

    async def create_session(self, *, title: str) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("opencode_session_title_invalid")
        result = await self._request_json(
            "POST",
            "/api/session",
            body={
                "title": title.strip(),
                "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],
            },
        )
        session = result.get("data") if isinstance(result, dict) else None
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise OpenCodeTransportError("opencode_invalid_session_response")
        if not _SESSION_ID.fullmatch(session["id"]):
            raise OpenCodeTransportError("opencode_invalid_session_id")
        title_value = session.get("title")
        safe_title = title_value[:120] if isinstance(title_value, str) else title.strip()
        return {"id": session["id"], "title": safe_title}

    async def list_pending_permissions(self, *, session_id: str) -> list[dict[str, Any]]:
        """Fetch and reduce pending approvals for this exact upstream session."""
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        result = await self._request_json("GET", f"/api/session/{session_id}/permission")
        items = result.get("data") if isinstance(result, dict) else None
        if not isinstance(items, list) or len(items) > 100:
            raise OpenCodeTransportError("opencode_invalid_permission_catalog")
        return [opencode_contract.normalize_permission_request(item, session_id) for item in items]

    async def reply_permission(self, *, session_id: str, request_id: str, decision: str) -> None:
        """Resolve one session-owned request; permanent approvals are impossible."""
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        body = opencode_contract.permission_reply_body(request_id, decision)
        path = f"/api/session/{session_id}/permission/{request_id}/reply"
        if not re.fullmatch(r"/api/session/ses[A-Za-z0-9_-]{1,128}/permission/per[A-Za-z0-9_-]{1,128}/reply", path):
            raise ValueError("opencode_route_not_allowed")
        try:
            response = await self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc
        if 300 <= response.status_code < 400:
            raise OpenCodeTransportError("opencode_redirect_rejected")
        if response.status_code not in (200, 204):
            raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
        if len(response.content) > 4096:
            raise OpenCodeTransportError("opencode_response_too_large")

    async def submit_prompt_async(self, *, session_id: str, prompt: str) -> None:
        """Durably admit one bounded text prompt to the exact task-owned session.

        OpenCode 2.x uses POST /api/session/:sessionID/prompt with a PromptInput
        body (text/files/agents/skills), not the legacy prompt_async route.
        Callers must validate the durable SULY session/task/lease mapping first.
        """
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > _MAX_PROMPT_CHARS:
            raise ValueError("opencode_prompt_invalid")
        if any(ord(char) < 32 and char not in "\\n\\r\\t" for char in prompt):
            raise ValueError("opencode_prompt_invalid")
        path = f"/api/session/{session_id}/prompt"
        if not re.fullmatch(r"/api/session/ses[A-Za-z0-9_-]{1,128}/prompt", path):
            raise ValueError("opencode_route_not_allowed")
        try:
            response = await self._client.post(path, json={"text": prompt.strip()})
        except httpx.HTTPError as exc:
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc
        if 300 <= response.status_code < 400:
            raise OpenCodeTransportError("opencode_redirect_rejected")
        if response.status_code != 200:
            raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
        if len(response.content) > 16_384:
            raise OpenCodeTransportError("opencode_response_too_large")
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise OpenCodeTransportError("opencode_invalid_json") from exc
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            raise OpenCodeTransportError("opencode_prompt_not_accepted")

    async def abort_session(self, *, session_id: str) -> bool:
        """Interrupt execution for the exact session; SULY remains task-state authority."""
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        path = f"/api/session/{session_id}/interrupt"
        if not re.fullmatch(r"/api/session/ses[A-Za-z0-9_-]{1,128}/interrupt", path):
            raise ValueError("opencode_route_not_allowed")
        try:
            response = await self._client.post(path, params={"resume": "false"})
        except httpx.HTTPError as exc:
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc
        if 300 <= response.status_code < 400:
            raise OpenCodeTransportError("opencode_redirect_rejected")
        if response.status_code != 200:
            raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
        if len(response.content) > 4096:
            raise OpenCodeTransportError("opencode_response_too_large")
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise OpenCodeTransportError("opencode_invalid_json") from exc
        if not isinstance(value, dict) or not isinstance(value.get("interrupted"), bool):
            raise OpenCodeTransportError("opencode_interrupt_not_confirmed")
        return value["interrupted"]

    async def list_skills(self) -> list[dict[str, Any]]:
        result = await self._request_json("GET", "/api/skill")
        items = result.get("data") if isinstance(result, dict) else None
        if not isinstance(items, list) or len(items) > 500:
            raise OpenCodeTransportError("opencode_invalid_skill_catalog")
        # Return only bounded, non-executable catalog metadata; never skill source.
        safe: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name, description = item.get("name"), item.get("description")
            if isinstance(name, str) and 1 <= len(name) <= 100:
                safe.append({
                    "name": name,
                    "description": description[:500] if isinstance(description, str) else "",
                })
        return safe

    async def list_providers(self) -> list[dict[str, Any]]:
        result = await self._request_json("GET", "/api/provider")
        items = result.get("data") if isinstance(result, dict) else None
        if not isinstance(items, list) or len(items) > 200:
            raise OpenCodeTransportError("opencode_invalid_provider_catalog")
        safe: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            provider_id, name = item.get("id"), item.get("name")
            if isinstance(provider_id, str) and 1 <= len(provider_id) <= 100:
                safe.append({
                    "id": provider_id,
                    "name": name[:120] if isinstance(name, str) else provider_id,
                })
        return safe
