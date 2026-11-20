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
        return httpx.Response(200, json={"data": {"id": "ses_test_123456", "title": "SULY task"}})

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
            lambda request: httpx.Response(200, json={"data": {"id": "not-a-session"}})
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="session_id"):
            await client.create_session(title="valid")


@pytest.mark.asyncio
async def test_catalog_endpoints_unwrap_upstream_envelopes_and_drop_sensitive_fields():
    async def handler(request):
        if request.url.path == "/api/skill":
            return httpx.Response(200, json={"location": {"path": "/private"}, "data": [
                {"name": "python", "description": "Python helper", "content": "secret skill source", "path": "/private/SKILL.md"},
                {"name": "x" * 101, "content": "ignored"},
            ]})
        if request.url.path == "/api/provider":
            return httpx.Response(200, json={"location": {"path": "/private"}, "data": [
                {"id": "openai", "name": "OpenAI", "headers": {"Authorization": "secret"}},
            ]})
        return httpx.Response(404)

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        assert await client.list_skills() == [{"name": "python", "description": "Python helper"}]
        assert await client.list_providers() == [{"id": "openai", "name": "OpenAI"}]


@pytest.mark.asyncio
async def test_pending_permissions_are_session_bound_and_reduced():
    async def handler(request):
        assert request.url.path == f"/api/session/ses_taskrun_123456789/permission"
        return httpx.Response(200, json={"data": [{
            "id": "per_request_123456",
            "sessionID": "ses_taskrun_123456789",
            "action": "bash",
            "resources": ["git status"],
            "message": "private model text",
            "metadata": {"secret": "drop"},
        }]})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.list_pending_permissions(session_id="ses_taskrun_123456789")

    assert result == [{
        "request_id": "per_request_123456",
        "session_id": "ses_taskrun_123456789",
        "action": "bash",
        "resources": ["git status"],
    }]


@pytest.mark.asyncio
async def test_permission_reply_only_allows_once_or_reject_and_never_remember():
    seen = {}

    async def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(204)

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        await client.reply_permission(
            session_id="ses_taskrun_123456789",
            request_id="per_request_123456",
            decision="once",
        )
        with pytest.raises(ValueError, match="decision_invalid"):
            await client.reply_permission(
                session_id="ses_taskrun_123456789",
                request_id="per_request_123456",
                decision="always",
            )

    assert seen["path"] == "/api/session/ses_taskrun_123456789/permission/per_request_123456/reply"
    assert seen["body"] == '{"decision":"once"}'


@pytest.mark.asyncio
async def test_pending_permissions_reject_cross_session_payload():
    async def handler(request):
        return httpx.Response(200, json={"data": [{
            "id": "per_request_123456",
            "sessionID": "ses_other_session_123456",
            "action": "bash",
            "resources": ["git status"],
        }]})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValueError, match="session_mismatch"):
            await client.list_pending_permissions(session_id="ses_taskrun_123456789")


@pytest.mark.asyncio
async def test_prompt_async_is_session_scoped_bounded_and_sends_text_only():
    seen = {}

    async def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(204)

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        await client.submit_prompt_async(
            session_id="ses_taskrun_123456789",
            prompt="  Fix the failing unit tests.  ",
        )
        with pytest.raises(ValueError, match="prompt_invalid"):
            await client.submit_prompt_async(
                session_id="ses_taskrun_123456789",
                prompt="\\x00invalid",
            )
        with pytest.raises(ValueError, match="prompt_invalid"):
            await client.submit_prompt_async(
                session_id="ses_taskrun_123456789",
                prompt="x" * 32001,
            )

    assert seen["path"] == "/api/session/ses_taskrun_123456789/prompt_async"
    assert seen["body"] == '{"parts":[{"type":"text","text":"Fix the failing unit tests."}]}'


@pytest.mark.asyncio
async def test_prompt_async_rejects_non_204_and_redirects():
    async def redirect(request):
        return httpx.Response(307, headers={"location": "https://attacker.example/"})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(redirect),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="redirect_rejected"):
            await client.submit_prompt_async(
                session_id="ses_taskrun_123456789", prompt="Do work"
            )

    async def unexpected(request):
        return httpx.Response(200, json={"data": {"secret": "not surfaced"}})

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(unexpected),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="status_200"):
            await client.submit_prompt_async(
                session_id="ses_taskrun_123456789", prompt="Do work"
            )


@pytest.mark.asyncio
async def test_abort_session_requires_confirmed_boolean_and_exact_session():
    seen = {}

    async def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json=True)

    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(handler),
    ) as client:
        await client.abort_session(session_id="ses_taskrun_123456789")
        with pytest.raises(ValueError, match="session_id_invalid"):
            await client.abort_session(session_id="../other")

    assert seen["path"] == "/api/session/ses_taskrun_123456789/abort"


@pytest.mark.asyncio
async def test_abort_session_fails_closed_when_upstream_does_not_confirm():
    async with OpenCodeHTTPClient(
        lease(), task_id=TASK_ID, engine_run_id=RUN_ID,
        allowed_origins=ORIGINS, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=False)
        ),
    ) as client:
        with pytest.raises(OpenCodeTransportError, match="abort_not_confirmed"):
            await client.abort_session(session_id="ses_taskrun_123456789")
