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


def lease(**overrides):
    values = {
        "runtime_id": str(uuid4()),
        "task_id": TASK_ID,
        "engine_run_id": RUN_ID,
        "engine_id": "opencode",
        "base_url": ORIGIN,
        "access_token": "t" * 48,
        "expires_at": time() + 1200,
    }
    values.update(overrides)
    return RuntimeLease(**values)


@pytest.mark.asyncio
async def test_client_health_uses_basic_auth_and_fixed_https_origin():
    seen = {}

    async def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"version": "2.3.0"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        assert await client.health() == {"version": "2.3.0"}

    assert seen["url"] == ORIGIN + "/api/info"
    assert seen["auth"].startswith("Basic ")


@pytest.mark.asyncio
async def test_create_session_always_uses_fail_closed_ask_permissions():
    seen = {}

    async def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"id": "ses_test_123456", "title": "SULY task"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.create_session(title="  SULY task  ")

    assert result == {"id": "ses_test_123456", "title": "SULY task"}
    assert '"effect":"ask"' in seen["body"]
    assert '"action":"*"' in seen["body"]


@pytest.mark.asyncio
async def test_client_rejects_wrong_task_or_unapproved_origin_before_network():
    with pytest.raises(ValueError, match="task_attempt_mismatch"):
        OpenCodeHTTPClient(
            lease(), task_id=str(uuid4()), engine_run_id=RUN_ID,
            allowed_origins=ORIGINS,
        )
    with pytest.raises(ValueError, match="base_url"):
        OpenCodeHTTPClient(
            lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
            allowed_origins=frozenset({"https://other.internal"}),
        )


@pytest.mark.asyncio
async def test_client_rejects_redirects_instead_of_forwarding_credentials():
    async def handler(request):
        return httpx.Response(302, headers={"location": "https://attacker.example/"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="redirect_rejected"):
            await client.health()


@pytest.mark.asyncio
async def test_client_rejects_non_json_and_oversized_responses():
    async def html_handler(request):
        return httpx.Response(200, text="<html>no</html>", headers={"content-type": "text/html"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(html_handler),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="content_type"):
            await client.health()

    async def huge_handler(request):
        return httpx.Response(200, content=b" " * 1_048_577, headers={"content-type": "application/json"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(huge_handler),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="too_large"):
            await client.health()


@pytest.mark.asyncio
async def test_client_never_exposes_credentials_or_response_body_in_transport_errors():
    async def handler(request):
        raise httpx.ConnectError("sensitive-url-and-token-must-not-appear")

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OpenCodeTransportError) as error:
            await client.health()
    assert "sensitive-url" not in str(error.value)
    assert "t" * 48 not in str(error.value)


@pytest.mark.asyncio
async def test_client_rejects_arbitrary_routes_and_invalid_titles():
    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={})
        ),
    ) as client:
        with pytest.raises(ValueError, match="route_not_allowed"):
            await client._request_json("POST", "/api/pty")
        with pytest.raises(ValueError, match="title_invalid"):
            await client.create_session(title=" ")


@pytest.mark.asyncio
async def test_client_rejects_malformed_session_response():
    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": "not-a-session"})
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="session_id"):
            await client.create_session(title="valid")
