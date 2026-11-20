"""Bounded OpenCode SSE consumer that persists a privacy-filtered event feed."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx

from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore

_SESSION = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_SAFE_FIELDS = frozenset({
    "sessionID", "sessionId", "messageID", "messageId", "partID",
    "permissionID", "permission", "status", "title", "reason",
})


def iter_sse_data(chunks: Iterator[bytes], *, max_line: int = 8192, max_event: int = 16384):
    """Parse SSE data frames incrementally; reject oversized unterminated frames."""
    buffer = bytearray()
    data_lines: list[bytes] = []
    event_size = 0
    for chunk in chunks:
        if not isinstance(chunk, (bytes, bytearray)):
            raise ValueError("sse_chunk_invalid")
        for byte in chunk:
            if byte == 10:
                line = bytes(buffer).rstrip(b"\r")
                buffer.clear()
                if not line:
                    if data_lines:
                        yield b"\n".join(data_lines)
                    data_lines = []
                    event_size = 0
                    continue
                if len(line) > max_line:
                    raise ValueError("sse_line_too_large")
                if line.startswith(b":"):
                    continue
                if line.startswith(b"data:"):
                    value = line[5:]
                    if value.startswith(b" "):
                        value = value[1:]
                    event_size += len(value)
                    if event_size > max_event:
                        raise ValueError("sse_event_too_large")
                    data_lines.append(value)
            else:
                buffer.append(byte)
                if len(buffer) > max_line:
                    raise ValueError("sse_line_too_large")
    if buffer or data_lines:
        raise ValueError("sse_stream_ended_mid_event")


class OpenCodeEventConsumer:
    def __init__(self, *, store: OpenCodeLifecycleStore, timeout: float = 30.0) -> None:
        self._store = store
        self._timeout = timeout

    @staticmethod
    def _url(base_url: str, gateway_path: str) -> str:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("opencode_gateway_origin_invalid")
        if not re.fullmatch(r"/v1/runtime-gateway/[0-9a-f-]{36}", gateway_path):
            raise ValueError("opencode_gateway_path_invalid")
        return base_url.rstrip("/") + gateway_path + "/event"

    def consume(
        self, *, user_id: str, run_id: str, session_id: str, base_url: str,
        gateway_path: str, runtime_token: str, sequence_start: int = 1,
        max_events: int = 500, max_seconds: int = 25,
    ) -> int:
        if not _SESSION.fullmatch(session_id or ""):
            raise ValueError("opencode_session_id_invalid")
        if not 1 <= max_events <= 500 or not 1 <= max_seconds <= 30 or sequence_start < 1:
            raise ValueError("opencode_event_consumer_limits_invalid")
        url = self._url(base_url, gateway_path)
        deadline = time.monotonic() + max_seconds
        saved = 0
        with httpx.Client(
            timeout=httpx.Timeout(self._timeout, connect=5, read=max_seconds + 5),
            follow_redirects=False, trust_env=False,
            headers={"Authorization": f"Bearer {runtime_token}", "Accept": "text/event-stream"},
        ) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200 or response.headers.get("content-type", "").split(";", 1)[0].lower() != "text/event-stream":
                    raise RuntimeError("opencode_event_stream_unavailable")
                def chunks():
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if time.monotonic() > deadline or saved >= max_events:
                            break
                        yield chunk
                for raw in iter_sse_data(chunks()):
                    if time.monotonic() > deadline or saved >= max_events:
                        break
                    try:
                        event = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    if not isinstance(event_type, str) or len(event_type) > 100:
                        continue
                    properties = event.get("properties")
                    if not isinstance(properties, dict):
                        properties = {}
                    event_session = properties.get("sessionID") or properties.get("sessionId")
                    if event_session is not None and event_session != session_id:
                        continue
                    safe = {key: properties[key] for key in _SAFE_FIELDS if key in properties}
                    safe["upstream_type"] = event_type[:100]
                    if event_type.startswith("permission."):
                        mapped = "permission.requested"
                    elif event_type.endswith(".error"):
                        mapped = "task.failed"
                    elif event_type.endswith(".idle"):
                        mapped = "task.completed"
                    else:
                        mapped = "task.status"
                    self._store.append_event(
                        user_id=user_id, run_id=run_id,
                        sequence=sequence_start + saved, event_type=mapped, payload=safe,
                    )
                    saved += 1
        return saved
