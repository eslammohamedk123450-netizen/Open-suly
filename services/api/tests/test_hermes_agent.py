from threading import Event
from time import time
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.services import hermes_agent
from app.services.runtime_broker_contract import RuntimeLease


def settings(**overrides):
    values = {
        "hermes_agent_enabled": True,
        "hermes_agent_isolation_confirmed": True,
        "hermes_agent_base_url": "http://hermes:8642",
        "hermes_agent_api_key": SecretStr("test-only-token"),
        "hermes_agent_timeout_seconds": 90.0,
        "hermes_agent_max_output_chars": 12000,
        "runtime_provisioner_allowed_origins": frozenset({"https://hermes-runtime.internal:8443"}),
    }
    values.update(overrides)
    return type("Settings", (), values)()


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise hermes_agent.httpx.HTTPStatusError(
                "sensitive upstream body",
                request=hermes_agent.httpx.Request("GET", "http://hermes"),
                response=hermes_agent.httpx.Response(self.status_code),
            )

    def json(self):
        return self.payload


def invoke(monkeypatch, client, **kwargs):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: client)
    kwargs.setdefault("idempotency_key", "suly-test-run-0001")
    kwargs.setdefault("on_run_started", lambda _run_id: True)
    return hermes_agent.run_agent_turn("Do a safe task", **kwargs)


def test_hermes_bridge_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_enabled=False),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="disabled"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


def test_hermes_bridge_requires_isolation_attestation(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_isolation_confirmed=False),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="isolation"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


def test_hermes_bridge_requires_url_and_key(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_api_key=None),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="not configured"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


@pytest.mark.parametrize("base_url", [
    "ftp://hermes:8642",
    "http://user:pass@hermes:8642",
    "http://hermes:8642?token=secret",
    "http://hermes:8642#fragment",
    "http:///missing-host",
])
def test_hermes_bridge_rejects_unsafe_base_url(monkeypatch, base_url):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_base_url=base_url),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="base URL"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


def test_safe_run_event_only_exposes_bounded_metadata():
    payload = {
        "event": "tool.started",
        "run_id": "run_safe_123",
        "seq": 7,
        "timestamp": 123.5,
        "tool": "terminal",
        "preview": "echo secret-token",
        "text": "private reasoning",
        "output": "private output",
    }
    assert hermes_agent._safe_run_event(payload, "run_safe_123") == {
        "event": "tool.started",
        "seq": 7,
        "timestamp": 123.5,
    }


@pytest.mark.parametrize("payload", [
    {"event": "message.interim", "run_id": "run_safe_123", "text": "private"},
    {"event": "tool.started", "run_id": "another-run"},
    {"event": "unknown.event", "run_id": "run_safe_123"},
    ["not", "an", "object"],
])
def test_safe_run_event_drops_untrusted_or_content_bearing_events(payload):
    assert hermes_agent._safe_run_event(payload, "run_safe_123") is None


def test_safe_run_event_projects_only_bounded_subagent_metadata():
    result = hermes_agent._safe_run_event({
        "event": "subagent.start",
        "run_id": "run_safe_123",
        "subagent_id": "child_01",
        "delegation_id": "delegation_01",
        "parent_id": "parent_01",
        "child_session_id": "session_01",
        "status": "running",
        "task_index": 1,
        "task_count": 3,
        "depth": 1,
        "tool_count": 2,
        "input_tokens": 1200,
        "output_tokens": 300,
        "duration_seconds": 1.25,
        "goal": "private delegation prompt",
        "summary": "private child output",
    }, "run_safe_123")
    assert result == {
        "event": "subagent.start",
        "metadata": {
            "subagent_id": "child_01",
            "delegation_id": "delegation_01",
            "parent_id": "parent_01",
            "child_session_id": "session_01",
            "status": "running",
            "task_index": 1,
            "task_count": 3,
            "depth": 1,
            "tool_count": 2,
            "input_tokens": 1200,
            "output_tokens": 300,
            "duration_seconds": 1.25,
        },
    }


@pytest.mark.parametrize("payload", [
    {"event": "subagent.start", "run_id": "run_safe_123"},
    {"event": "subagent.complete", "run_id": "run_safe_123", "subagent_id": "../escape"},
    {"event": "subagent.start", "run_id": "run_safe_123", "subagent_id": "child", "depth": True},
    {"event": "subagent.start", "run_id": "run_safe_123", "subagent_id": "child", "duration_seconds": 86401},
    {"event": "subagent.complete", "run_id": "run_safe_123", "subagent_id": "child", "status": "unknown"},
])
def test_safe_run_event_drops_invalid_subagent_metadata(payload):
    assert hermes_agent._safe_run_event(payload, "run_safe_123") is None


@pytest.mark.parametrize("payload", [
    {"event": "approval.request", "run_id": "run_safe_123"},
    {"event": "approval.request", "run_id": "run_safe_123", "request_id": "bad\nrequest"},
    {"event": "approval.responded", "run_id": "run_safe_123", "request_id": "approval-1"},
    {"event": "approval.responded", "run_id": "run_safe_123", "request_id": "approval-1", "choice": "always"},
    {"event": "approval.responded", "run_id": "run_safe_123", "request_id": "approval-1", "choice": "session"},
])
def test_safe_run_event_drops_malformed_or_unsupported_approval_events(payload):
    assert hermes_agent._safe_run_event(payload, "run_safe_123") is None


def test_safe_run_event_keeps_only_exact_approval_request_metadata():
    assert hermes_agent._safe_run_event({
        "event": "approval.request",
        "run_id": "run_safe_123",
        "request_id": "approval-req_123",
        "command": "must not persist",
        "description": "must not persist",
    }, "run_safe_123") == {
        "event": "approval.request",
        "approval_request_id": "approval-req_123",
    }
    assert hermes_agent._safe_run_event({
        "event": "approval.responded",
        "run_id": "run_safe_123",
        "request_id": "approval-req_123",
        "choice": "once",
        "command": "must not persist",
    }, "run_safe_123") == {
        "event": "approval.responded",
        "approval_request_id": "approval-req_123",
        "approval_choice": "once",
    }


def test_hermes_sse_consumer_parses_events_and_never_forwards_free_text():
    import asyncio
    import json

    class StreamResponse:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        def raise_for_status(self):
            return None
        async def aiter_lines(self):
            events = [
                {"event": "tool.started", "run_id": "run_sse_123", "seq": 1,
                 "timestamp": 10.0, "preview": "private command"},
                {"event": "message.interim", "run_id": "run_sse_123", "seq": 2,
                 "timestamp": 11.0, "text": "private assistant text"},
                {"event": "run.completed", "run_id": "run_sse_123", "seq": 3,
                 "timestamp": 12.0, "output": "private final output"},
            ]
            for event in events:
                yield "data: " + json.dumps(event)
                yield ""

    class Client:
        def stream(self, method, url, **kwargs):
            assert method == "GET"
            assert url.endswith("/v1/runs/run_sse_123/events")
            assert kwargs["headers"]["Authorization"] == "Bearer test-only-token"
            return StreamResponse()

    received = []
    asyncio.run(hermes_agent._consume_run_events(
        Client(),
        "http://hermes:8642",
        "run_sse_123",
        {"Authorization": "Bearer test-only-token"},
        received.append,
    ))
    assert received == [
        {"event": "tool.started", "seq": 1, "timestamp": 10.0},
        {"event": "run.completed", "seq": 3, "timestamp": 12.0},
    ]
    assert all("output" not in event and "text" not in event for event in received)


def test_hermes_sse_consumer_drops_aggregate_oversized_event_and_resumes():
    import asyncio
    import json

    class StreamResponse:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        def raise_for_status(self):
            return None
        async def aiter_lines(self):
            for _ in range(6):
                yield "data: " + ("x" * 50_000)
            yield ""
            yield "data: " + json.dumps({
                "event": "run.completed",
                "run_id": "run_sse_bounded",
                "seq": 2,
            })
            yield ""

    class Client:
        def stream(self, *_args, **_kwargs):
            return StreamResponse()

    received = []
    asyncio.run(hermes_agent._consume_run_events(
        Client(), "https://hermes-runtime.internal:8443", "run_sse_bounded",
        {"Authorization": "Bearer test-token"}, received.append,
    ))
    assert received == [{"event": "run.completed", "seq": 2}]


def test_hermes_native_runs_api_admits_polls_and_persists_run_id(monkeypatch):
    calls = []
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **kwargs):
            calls.append(("POST", url, kwargs))
            return Response({"run_id": "run_native_123", "status": "started"}, 202)
        async def get(self, url, **kwargs):
            calls.append(("GET", url, kwargs))
            return Response({
                "run_id": "run_native_123",
                "status": "completed",
                "output": "Task completed safely.",
            })

    persisted = []
    client_options = {}
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda **kwargs: client_options.update(kwargs) or Client(),
    )
    result = hermes_agent.run_agent_turn(
        "Do a safe task",
        idempotency_key="suly-test-run-0001",
        on_run_started=lambda run_id: persisted.append(run_id) or True,
    )
    assert result == {"engine": "hermes-agent", "content": "Task completed safely."}
    assert persisted == ["run_native_123"]
    assert calls[0][1] == "http://hermes:8642/v1/runs"
    assert calls[0][2]["headers"]["Authorization"] == "Bearer test-only-token"
    assert calls[0][2]["headers"]["Idempotency-Key"] == "suly-test-run-0001"
    assert calls[0][2]["json"] == {"input": "Do a safe task"}
    assert calls[1][1] == "http://hermes:8642/v1/runs/run_native_123"
    assert client_options["trust_env"] is False
    assert client_options["follow_redirects"] is False


@pytest.mark.parametrize("prompt", ["", "  ", "x" * 20001, None])
def test_hermes_bridge_rejects_invalid_prompt(monkeypatch, prompt):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="prompt"):
        hermes_agent.run_agent_turn(
            prompt,
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


@pytest.mark.parametrize("timeout", [True, False, 0, 301, "30"])
def test_hermes_bridge_rejects_invalid_timeout(monkeypatch, timeout):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="timeout"):
        hermes_agent.run_agent_turn(
            "hello",
            timeout_seconds=timeout,
            idempotency_key="test-timeout-key",
            on_run_started=lambda _run_id: True,
        )


def test_hermes_bridge_rejects_invalid_idempotency_key(monkeypatch):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="idempotency"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="contains spaces",
            on_run_started=lambda _run_id: True,
        )


def test_hermes_bridge_rejects_oversized_output(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_max_output_chars=256),
    )
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"run_id": "run_123"}, 202)
        async def get(self, *_args, **_kwargs):
            return Response({"status": "completed", "output": "x" * 257})

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="exceeded"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )


def test_hermes_bridge_redacts_upstream_http_error(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            raise hermes_agent.httpx.ConnectError("sensitive upstream response body")

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="request failed") as error:
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: True,
        )
    assert "sensitive upstream response body" not in str(error.value)


def test_hermes_bridge_stops_run_when_cancelled(monkeypatch):
    cancel_event = Event()
    calls = []
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **_kwargs):
            calls.append(("POST", url))
            if url.endswith("/v1/runs"):
                return Response({"run_id": "run_cancel_123"}, 202)
            return Response({"status": "stopping"}, 200)
        async def get(self, url, **_kwargs):
            calls.append(("GET", url))
            return Response({"status": "cancelled"})

    def persist(_run_id):
        cancel_event.set()
        return True

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentCancelled):
        hermes_agent.run_agent_turn(
            "long task",
            cancel_event=cancel_event,
            idempotency_key="test-cancel-key",
            on_run_started=persist,
        )
    assert any(method == "POST" and url.endswith("/run_cancel_123/stop") for method, url in calls)


def test_hermes_bridge_stops_run_if_suly_cannot_persist_reference(monkeypatch):
    calls = []
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **_kwargs):
            calls.append(url)
            return Response({"run_id": "run_unpersisted_123"}, 202)
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="persist"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-key",
            on_run_started=lambda _run_id: False,
        )
    assert calls[-1].endswith("/run_unpersisted_123/stop")



@pytest.mark.parametrize("run_id", ["../outside", "run/with/slash", "id with spaces", "é-run", ""])
def test_hermes_bridge_rejects_unsafe_upstream_run_id(monkeypatch, run_id):
    # لا نسمح لمعرف خارجي بتغيير مسار API أو حقن قيم غير متوقعة.
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"run_id": run_id}, 202)

    persisted = []
    with pytest.raises(hermes_agent.HermesAgentError, match="invalid run identifier"):
        invoke(monkeypatch, Client(), on_run_started=lambda value: persisted.append(value) or True)
    assert persisted == []


def test_hermes_bridge_rejects_non_object_status_payload(monkeypatch):
    # رد الحالة يجب أن يكون كائن JSON، وإلا نوقف المسار برسالة آمنة.
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"run_id": "run_safe_123"}, 202)
        async def get(self, *_args, **_kwargs):
            return Response(["unexpected", "payload"])

    with pytest.raises(hermes_agent.HermesAgentError, match="invalid run status"):
        invoke(monkeypatch, Client())


def test_hermes_stop_reconciliation_confirms_terminal_state(monkeypatch):
    calls = []
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **_kwargs):
            calls.append(("POST", url))
            return Response({"status": "stopping"})
        async def get(self, url, **_kwargs):
            calls.append(("GET", url))
            return Response({"status": "cancelled"})

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    assert hermes_agent.stop_agent_run("run_orphan_123", timeout_seconds=5) is True
    assert calls[0][1].endswith("/run_orphan_123/stop")
    assert calls[1][1].endswith("/run_orphan_123")


def test_hermes_stop_reconciliation_does_not_assume_stop_was_successful(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"status": "stopping"})
        async def get(self, *_args, **_kwargs):
            return Response({"status": "running"})

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    async def no_sleep(*_args):
        return None
    monkeypatch.setattr(hermes_agent.asyncio, "sleep", no_sleep)
    assert hermes_agent.stop_agent_run("run_orphan_123", timeout_seconds=1) is False


@pytest.mark.parametrize("run_id", ["../escape", "run/other", "é", ""])
def test_hermes_stop_reconciliation_rejects_unsafe_run_ids(monkeypatch, run_id):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="identifier"):
        hermes_agent.stop_agent_run(run_id)


def test_hermes_stop_reconciliation_requires_server_credentials(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_enabled=False, hermes_agent_isolation_confirmed=False,
                         hermes_agent_api_key=None),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="not configured"):
        hermes_agent.stop_agent_run("run_orphan_123")


def test_hermes_stop_reconciliation_still_works_after_new_runs_are_disabled(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"status": "stopping"})
        async def get(self, *_args, **_kwargs):
            return Response({"status": "cancelled"})

    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_enabled=False, hermes_agent_isolation_confirmed=False),
    )
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    assert hermes_agent.stop_agent_run("run_orphan_123", timeout_seconds=5) is True


def test_hermes_bridge_retries_transient_run_id_persistence_failure(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"run_id": "run_retry_123"}, 202)
        async def get(self, *_args, **_kwargs):
            return Response({"status": "completed", "output": "done"})

    attempts = []
    def persist(_run_id):
        attempts.append(_run_id)
        if len(attempts) == 1:
            raise RuntimeError("temporary database timeout")
        return True

    result = invoke(monkeypatch, Client(), on_run_started=persist)
    assert result["content"] == "done"
    assert attempts == ["run_retry_123", "run_retry_123"]


def test_hermes_bridge_stops_run_when_run_id_persistence_raises(monkeypatch):
    calls = []
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **_kwargs):
            calls.append(url)
            return Response({"run_id": "run_db_error_123"}, 202)

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    def fail(_run_id):
        raise RuntimeError("secret database detail")
    with pytest.raises(hermes_agent.HermesAgentError, match="could not persist"):
        hermes_agent.run_agent_turn(
            "hello",
            idempotency_key="test-db-error",
            on_run_started=fail,
        )
    assert calls[-1].endswith("/run_db_error_123/stop")



def test_safe_approval_event_keeps_only_opaque_request_identity():
    event = hermes_agent._safe_run_event({
        "run_id": "run_approval_123",
        "event": "approval.request",
        "seq": 10,
        "request_id": "approval-req_123",
        "command": "rm -rf /",
        "description": "sensitive command preview",
    }, "run_approval_123")
    assert event == {
        "event": "approval.request",
        "seq": 10,
        "approval_request_id": "approval-req_123",
    }


def test_safe_approval_response_keeps_only_supported_choice():
    event = hermes_agent._safe_run_event({
        "run_id": "run_approval_123",
        "event": "approval.responded",
        "seq": 11,
        "request_id": "approval-req_123",
        "choice": "once",
        "description": "must not persist",
    }, "run_approval_123")
    assert event == {
        "event": "approval.responded",
        "seq": 11,
        "approval_request_id": "approval-req_123",
        "approval_choice": "once",
    }


def test_safe_approval_event_ignores_unhashable_choice_value():
    event = hermes_agent._safe_run_event({
        "run_id": "run_approval_123",
        "event": "approval.responded",
        "request_id": "approval-req_123",
        "choice": {"unexpected": "object"},
    }, "run_approval_123")
    assert event is None


def test_safe_approval_event_drops_invalid_request_id_and_permanent_choice():
    event = hermes_agent._safe_run_event({
        "run_id": "run_approval_123",
        "event": "approval.responded",
        "request_id": "bad request id",
        "choice": "always",
    }, "run_approval_123")
    assert event is None


def test_hermes_approval_details_returns_only_upstream_redacted_display_fields(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response({
                "run_id": "run_approval_123",
                "status": "waiting_for_approval",
                "approval": {
                    "request_id": "approval-req_123",
                    "command": "git status",
                    "description": "Review repository status",
                    "choices": ["once", "session", "always", "deny"],
                    "reasoning": "must not be returned",
                },
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    result = hermes_agent.get_agent_approval_details("run_approval_123", "approval-req_123")
    assert result == {
        "request_id": "approval-req_123",
        "command": "git status",
        "description": "Review repository status",
    }
    assert calls[0][0].endswith("/v1/runs/run_approval_123")


def test_hermes_approval_details_normalizes_control_characters(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def get(self, *_args, **_kwargs):
            return Response({
                "run_id": "run_approval_123",
                "status": "waiting_for_approval",
                "approval": {
                    "request_id": "approval-req_123",
                    "command": "line1" + chr(10) + "line2" + chr(0) + chr(0x202E) + "tail",
                },
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    result = hermes_agent.get_agent_approval_details("run_approval_123", "approval-req_123")
    assert result["command"] == "line1 line2  tail"
    assert chr(0) not in result["command"]
    assert chr(0x202E) not in result["command"]


def test_hermes_approval_details_removes_bidi_and_c1_format_controls(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def get(self, *_args, **_kwargs):
            return Response({
                "run_id": "run_approval_123",
                "status": "waiting_for_approval",
                "approval": {
                    "request_id": "approval-req_123",
                    "command": "safe\u202Etxt\u0085end",
                },
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    result = hermes_agent.get_agent_approval_details("run_approval_123", "approval-req_123")
    assert result["command"] == "safe txt end"


def test_hermes_approval_details_rejects_wrong_run_state_or_request(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def get(self, *_args, **_kwargs):
            return Response({
                "run_id": "run_approval_123",
                "status": "running",
                "approval": {"request_id": "approval-req_123", "command": "do thing"},
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="no longer pending"):
        hermes_agent.get_agent_approval_details("run_approval_123", "approval-req_123")


def test_hermes_approval_resolves_exact_request_with_once_choice(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response({
                "run_id": "run_approval_123",
                "request_id": "approval-req_123",
                "choice": "once",
                "resolved": 1,
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    assert hermes_agent.resolve_agent_approval(
        "run_approval_123", "approval-req_123", "once"
    ) is True
    assert calls == [(
        "http://hermes:8642/v1/runs/run_approval_123/approval",
        {
            "headers": {"Authorization": "Bearer test-only-token"},
            "json": {"request_id": "approval-req_123", "choice": "once"},
        },
    )]


@pytest.mark.parametrize("choice", ["always", "session", "approve", "", [], {}])
def test_hermes_approval_rejects_persistent_or_unknown_choices(monkeypatch, choice):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="once or deny"):
        hermes_agent.resolve_agent_approval("run_approval_123", "approval-req_123", choice)


def test_hermes_approval_rejects_invalid_request_id(monkeypatch):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="request identifier"):
        hermes_agent.resolve_agent_approval("run_approval_123", "bad request id", "once")


def test_hermes_approval_rejects_mismatched_or_unresolved_response(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({
                "run_id": "run_approval_123",
                "request_id": "another-request",
                "choice": "once",
                "resolved": 1,
            })

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="request identifier"):
        hermes_agent.resolve_agent_approval("run_approval_123", "approval-req_123", "once")


def test_hermes_steer_targets_one_existing_run_with_bounded_input(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response({"run_id": "run_steer_123", "accepted": True})

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    assert hermes_agent.steer_agent_run("run_steer_123", "Focus on the failing test") is True
    assert calls == [(
        "http://hermes:8642/v1/runs/run_steer_123/steer",
        {
            "headers": {"Authorization": "Bearer test-only-token"},
            "json": {"input": "Focus on the failing test"},
        },
    )]


@pytest.mark.parametrize("run_id,text", [
    ("../other-run", "hello"),
    ("run_safe_123", ""),
    ("run_safe_123", "x" * 20001),
])
def test_hermes_steer_rejects_invalid_run_or_input(monkeypatch, run_id, text):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError):
        hermes_agent.steer_agent_run(run_id, text)


def test_hermes_steer_rejects_unaccepted_or_mismatched_response(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            return Response({"run_id": "another-run", "accepted": True})

    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kw: Client())
    with pytest.raises(hermes_agent.HermesAgentError, match="did not match"):
        hermes_agent.steer_agent_run("run_steer_123", "please continue")



def make_hermes_runtime_lease():
    runtime_id = str(uuid4())
    task_id = str(uuid4())
    engine_run_id = str(uuid4())
    return RuntimeLease(
        runtime_id=runtime_id,
        task_id=task_id,
        engine_run_id=engine_run_id,
        engine_id="hermes-agent",
        base_url="https://hermes-runtime.internal:8443",
        access_token="x" * 48,
        expires_at=time() + 1800,
        gateway_path=f"/v1/runtime-gateway/{runtime_id}",
    ), task_id, engine_run_id


def test_runtime_credentials_accepts_exact_task_lease_without_shared_endpoint():
    lease, task_id, engine_run_id = make_hermes_runtime_lease()
    configured = settings(
        hermes_agent_isolation_confirmed=False,
        hermes_agent_base_url=None,
        hermes_agent_api_key=None,
    )
    base_url, token = hermes_agent._runtime_credentials(
        configured,
        runtime_lease=lease,
        task_id=task_id,
        engine_run_id=engine_run_id,
    )
    assert base_url == (
        f"{lease.base_url}/v1/runtime-gateway/{lease.runtime_id}"
    )
    assert token == lease.access_token


def test_runtime_credentials_rejects_cross_task_or_cross_engine_lease():
    lease, task_id, engine_run_id = make_hermes_runtime_lease()
    configured = settings(runtime_provisioner_allowed_origins=frozenset({
        "https://hermes-runtime.internal:8443",
    }))
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="lease is invalid"):
        hermes_agent._runtime_credentials(
            configured,
            runtime_lease=lease,
            task_id=str(uuid4()),
            engine_run_id=engine_run_id,
        )


def test_hermes_run_uses_task_lease_url_and_short_lived_token(monkeypatch):
    lease, task_id, engine_run_id = make_hermes_runtime_lease()
    configured = settings(
        hermes_agent_isolation_confirmed=False,
        hermes_agent_base_url=None,
        hermes_agent_api_key=None,
    )
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: configured)

    class Client:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            self.calls.append(("POST", url, kwargs))
            return Response({"run_id": "run_lease_123"})

        async def get(self, url, **kwargs):
            self.calls.append(("GET", url, kwargs))
            return Response({
                "run_id": "run_lease_123",
                "status": "completed",
                "output": "lease-scoped result",
            })

    client = Client()
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda **_kwargs: client)
    persisted = []
    result = hermes_agent.run_agent_turn(
        "run in isolated task runtime",
        idempotency_key="suly-task-runtime-lease",
        on_run_started=lambda upstream_id: persisted.append(upstream_id) or True,
        runtime_lease=lease,
        task_id=task_id,
        engine_run_id=engine_run_id,
    )
    assert result == {"engine": "hermes-agent", "content": "lease-scoped result"}
    assert persisted == ["run_lease_123"]
    assert len(client.calls) == 2
    assert all(
        call[1].startswith(
            f"{lease.base_url}{lease.gateway_path}/v1/runs"
        )
        for call in client.calls
    )
    assert all(
        call[2]["headers"]["Authorization"] == f"Bearer {lease.access_token}"
        for call in client.calls
    )
