from __future__ import annotations

from time import time
from uuid import uuid4

import httpx
import pytest

from app.services.opencode_http import OpenCodeHTTPClient, OpenCodeTransportError
from app.services.runtime_broker_contract import RuntimeLease

TASK_ID = str(uuid4())
RUN_ID = str(uuid4())
ORIGIN = "https://opencode-runtime.internal:8443"
ORIGINS = frozenset({ORIGIN})


def make_lease() -> RuntimeLease:
    return RuntimeLease(
        runtime_id=str(uuid4()),
        task_id=TASK_ID,
        engine_run_id=RUN_ID,
        engine_id="opencode",
        base_url=ORIGIN,
        access_token="t" * 48,
        expires_at=time() + 1200,
    )


@pytest.mark.asyncio
async def test_event_stream_returns_only_session_bound_safe_metadata():
    event = {
        "id": "evt_run_123456",
        "type": "session.execution.started",
        "created": 1_800_000_000,
        "data": {
            "sessionID": "ses_taskrun_123456789",
            "prompt": "private prompt must never escape",
            "tool": {"input": "secret command"},
            "directory": "/private/workspace",
        },
    }
    wrong_session = {
        "id": "evt_other_123456",
        "type": "session.execution.succeeded",
        "data": {"sessionID": "ses_other_session_123456", "output": "private"},
    }
    body = (
        "event: message\n"
        f"data: {__import__('json').dumps(event)}\n\n"
        f"data: {__import__('json').dumps(wrong_session)}\n\n"
    ).encode()

    async def handler(request):
        assert request.url.path == "/api/event"
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    async with OpenCodeHTTPClient(
        make_lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        result = [
            item async for item in client.iter_safe_events(
                session_id="ses_taskrun_123456789"
            )
        ]

    assert result == [{
        "event": "session.execution.started",
        "created": 1_800_000_000.0,
    }]
    assert "prompt" not in str(result)
    assert "directory" not in str(result)


@pytest.mark.asyncio
async def test_event_stream_drops_unknown_and_permission_events_without_valid_ids():
    import json

    events = [
        {"id": "evt_1", "type": "tool.execute", "data": {"sessionID": "ses_taskrun_123456789"}},
        {"id": "evt_2", "type": "permission.asked", "data": {
            "sessionID": "ses_taskrun_123456789", "id": "not-a-permission-id"
        }},
    ]
    body = "".join(f"data: {json.dumps(item)}\n\n" for item in events)

    async with OpenCodeHTTPClient(
        make_lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        ),
    ) as client:
        result = [
            item async for item in client.iter_safe_events(
                session_id="ses_taskrun_123456789"
            )
        ]
    assert result == []


@pytest.mark.asyncio
async def test_event_stream_rejects_redirect_and_wrong_content_type():
    async with OpenCodeHTTPClient(
        make_lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(
                307, headers={"location": "https://attacker.invalid/"}
            )
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="redirect_rejected"):
            _ = [
                item async for item in client.iter_safe_events(
                    session_id="ses_taskrun_123456789"
                )
            ]

    async with OpenCodeHTTPClient(
        make_lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": []})
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="event_content_type"):
            _ = [
                item async for item in client.iter_safe_events(
                    session_id="ses_taskrun_123456789"
                )
            ]


@pytest.mark.asyncio
async def test_event_stream_enforces_line_size_and_parameter_bounds():
    body = "data: " + ("x" * 400) + "\n\n"

    async with OpenCodeHTTPClient(
        make_lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="event_too_large"):
            _ = [
                item async for item in client.iter_safe_events(
                    session_id="ses_taskrun_123456789", max_event_bytes=256
                )
            ]
        with pytest.raises(ValueError, match="event_limit_invalid"):
            _ = [
                item async for item in client.iter_safe_events(
                    session_id="ses_taskrun_123456789", max_events=0
                )
            ]
