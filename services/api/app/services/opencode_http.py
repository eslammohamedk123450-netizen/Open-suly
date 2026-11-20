"""Task-scoped, fail-closed HTTP client for the pinned OpenCode server.

This is a transport adapter only: it never provisions a runtime, accepts a client
URL, forwards local file paths, or enables shell/PTY/MCP/plugin capabilities.
Callers must obtain and validate a RuntimeLease before constructing it.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.runtime_broker_contract import RuntimeLease

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
        if (method, path) not in _ALLOWED_ROUTES:
            raise ValueError("opencode_route_not_allowed")
        try:
            response = await self._client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            # Deliberately omit URL, request headers, response body and exception text.
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc
        if 300 <= response.status_code < 400:
            raise OpenCodeTransportError("opencode_redirect_rejected")
        if response.status_code < 200 or response.status_code >= 300:
            raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise OpenCodeTransportError("opencode_response_too_large")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise OpenCodeTransportError("opencode_invalid_content_type")
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise OpenCodeTransportError("opencode_invalid_json") from exc

    async def health(self) -> dict[str, Any]:
        result = await self._request_json("GET", "/api/info")
        if not isinstance(result, dict):
            raise OpenCodeTransportError("opencode_invalid_info_response")
        return result

    async def create_session(self, *, title: str) -> dict[str, Any]:
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("opencode_session_title_invalid")
        result = await self._request_json(
            "POST",
            "/api/session",
            body={
                "title": title.strip(),
                "permission": [{"action": "*", "resource": "*", "effect": "ask"}],
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            raise OpenCodeTransportError("opencode_invalid_session_response")
        if not _SESSION_ID.fullmatch(result["id"]):
            raise OpenCodeTransportError("opencode_invalid_session_id")
        return {"id": result["id"], "title": result.get("title")}

    async def list_skills(self) -> list[dict[str, Any]]:
        result = await self._request_json("GET", "/api/skill")
        if not isinstance(result, list) or len(result) > 500:
            raise OpenCodeTransportError("opencode_invalid_skill_catalog")
        # Return only bounded, non-executable catalog metadata; never skill source.
        safe: list[dict[str, Any]] = []
        for item in result:
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
        if not isinstance(result, list) or len(result) > 200:
            raise OpenCodeTransportError("opencode_invalid_provider_catalog")
        safe: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            provider_id, name = item.get("id"), item.get("name")
            if isinstance(provider_id, str) and 1 <= len(provider_id) <= 100:
                safe.append({
                    "id": provider_id,
                    "name": name[:120] if isinstance(name, str) else provider_id,
                })
        return safe

    async def aclose_session(self, session_id: str) -> None:
        # Session deletion is intentionally not exposed until durable SULY session
        # ownership and cleanup/reconciliation are implemented.
        if not _SESSION_ID.fullmatch(session_id) if isinstance(session_id, str) else True:
            raise ValueError("opencode_session_id_invalid")
        raise NotImplementedError("opencode_session_cleanup_requires_durable_session_binding")

