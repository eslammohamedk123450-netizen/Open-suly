"""Task-scoped, fail-closed HTTP client for the pinned OpenCode server.

This is a transport adapter only: it never provisions a runtime, accepts a client
URL, forwards local file paths, or enables shell/PTY/MCP/plugin capabilities.
Callers must obtain and validate a RuntimeLease before constructing it.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
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

    def _gateway_route(self, path: str) -> str:
        prefix = self._lease.gateway_path
        if prefix:
            return prefix + path
        return path


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
            async with self._client.stream(method, self._gateway_route(path), json=body) as response:
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

    async def _request_bounded_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        allowed_statuses: frozenset[int],
        max_bytes: int,
    ) -> Any:
        """Read a small JSON response with streaming byte limits and no redirects."""
        if not (path.startswith("/api/session/") and len(path) <= 512):
            raise ValueError("opencode_route_not_allowed")
        try:
            async with self._client.stream(method, self._gateway_route(path), json=body, params=params) as response:
                if 300 <= response.status_code < 400:
                    raise OpenCodeTransportError("opencode_redirect_rejected")
                if response.status_code not in allowed_statuses:
                    raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise OpenCodeTransportError("opencode_invalid_content_type")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise OpenCodeTransportError("opencode_response_too_large")
                    chunks.append(chunk)
        except OpenCodeTransportError:
            raise
        except httpx.HTTPError as exc:
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
            async with self._client.stream("POST", self._gateway_route(path), json=body) as response:
                if 300 <= response.status_code < 400:
                    raise OpenCodeTransportError("opencode_redirect_rejected")
                if response.status_code not in (200, 204):
                    raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > 4096:
                        raise OpenCodeTransportError("opencode_response_too_large")
        except OpenCodeTransportError:
            raise
        except httpx.HTTPError as exc:
            # Never include upstream URL, headers, response body, or credentials.
            raise OpenCodeTransportError("opencode_runtime_unreachable") from exc

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
        if any(ord(char) < 32 and char not in "\n\r\t" for char in prompt):
            raise ValueError("opencode_prompt_invalid")
        path = f"/api/session/{session_id}/prompt"
        if not re.fullmatch(r"/api/session/ses[A-Za-z0-9_-]{1,128}/prompt", path):
            raise ValueError("opencode_route_not_allowed")
        value = await self._request_bounded_json(
            "POST", path, body={"text": prompt.strip()},
            allowed_statuses=frozenset({200}), max_bytes=16_384,
        )
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            raise OpenCodeTransportError("opencode_prompt_not_accepted")

    async def abort_session(self, *, session_id: str) -> bool:
        """Interrupt execution for the exact session; SULY remains task-state authority."""
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        path = f"/api/session/{session_id}/interrupt"
        if not re.fullmatch(r"/api/session/ses[A-Za-z0-9_-]{1,128}/interrupt", path):
            raise ValueError("opencode_route_not_allowed")
        value = await self._request_bounded_json(
            "POST", path, params={"resume": "false"},
            allowed_statuses=frozenset({200}), max_bytes=4096,
        )
        if not isinstance(value, dict) or not isinstance(value.get("interrupted"), bool):
            raise OpenCodeTransportError("opencode_interrupt_not_confirmed")
        return value["interrupted"]

    async def iter_safe_events(
        self,
        *,
        session_id: str,
        max_events: int = 500,
        max_event_bytes: int = 16_384,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield only allowlisted metadata from OpenCode's server-wide SSE feed.

        The upstream feed is volatile and server-wide. This adapter is safe only
        because each RuntimeLease must represent one isolated task-attempt server;
        the reducer additionally binds every event to the expected session ID.
        Raw event payloads, prompts, tool arguments, reasoning, paths and output
        are never returned. SULY's durable task ledger remains authoritative.
        """
        if not _SESSION_ID.fullmatch(session_id):
            raise ValueError("opencode_session_id_invalid")
        if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 5000:
            raise ValueError("opencode_event_limit_invalid")
        if isinstance(max_event_bytes, bool) or not isinstance(max_event_bytes, int) or not 256 <= max_event_bytes <= 65_536:
            raise ValueError("opencode_event_size_invalid")

        yielded = 0
        data_lines: list[str] = []
        event_size = 0
        line_buffer = bytearray()
        try:
            async with self._client.stream(
                "GET", self._gateway_route("/api/event"), headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(60.0, connect=5.0, read=30.0),
            ) as response:
                if 300 <= response.status_code < 400:
                    raise OpenCodeTransportError("opencode_redirect_rejected")
                if response.status_code != 200:
                    raise OpenCodeTransportError(f"opencode_upstream_status_{response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "text/event-stream":
                    raise OpenCodeTransportError("opencode_invalid_event_content_type")

                # Parse bounded byte chunks ourselves. aiter_lines() can allocate an
                # arbitrarily large unterminated line before application limits run.
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    line_buffer.extend(chunk)
                    if len(line_buffer) > max_event_bytes and b"\\n" not in line_buffer:
                        raise OpenCodeTransportError("opencode_event_too_large")
                    while b"\\n" in line_buffer:
                        raw_line, _, remainder = line_buffer.partition(b"\\n")
                        line_buffer = bytearray(remainder)
                        if len(raw_line) > max_event_bytes:
                            raise OpenCodeTransportError("opencode_event_too_large")
                        if raw_line.endswith(b"\\r"):
                            raw_line = raw_line[:-1]
                        if not raw_line:
                            if data_lines:
                                raw = "\\n".join(data_lines)
                                data_lines.clear()
                                event_size = 0
                                try:
                                    envelope = json.loads(raw)
                                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                                    continue
                                safe = opencode_contract.safe_event_metadata(envelope, session_id)
                                if safe is not None:
                                    yield safe
                                    yielded += 1
                                    if yielded >= max_events:
                                        return
                            continue
                        if raw_line.startswith(b":"):
                            continue
                        if raw_line.startswith(b"data:"):
                            value_bytes = raw_line[5:]
                            if value_bytes.startswith(b" "):
                                value_bytes = value_bytes[1:]
                            event_size += len(value_bytes) + (1 if data_lines else 0)
                            if event_size > max_event_bytes:
                                raise OpenCodeTransportError("opencode_event_too_large")
                            try:
                                data_lines.append(value_bytes.decode("utf-8", errors="strict"))
                            except UnicodeDecodeError:
                                data_lines.clear()
                                event_size = 0
                                continue
                    if len(line_buffer) > max_event_bytes:
                        raise OpenCodeTransportError("opencode_event_too_large")
        except OpenCodeTransportError:
            raise
        except httpx.HTTPError as exc:
            raise OpenCodeTransportError("opencode_event_stream_unavailable") from exc

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
