from threading import Event

import pytest
from pydantic import SecretStr

from app.services import hermes_agent


def settings(**overrides):
    values = {
        "hermes_agent_enabled": True,
        "hermes_agent_isolation_confirmed": True,
        "hermes_agent_base_url": "http://hermes:8642",
        "hermes_agent_api_key": SecretStr("test-only-token"),
        "hermes_agent_timeout_seconds": 90.0,
        "hermes_agent_max_output_chars": 12000,
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
    result = invoke(
        monkeypatch,
        Client(),
        on_run_started=lambda run_id: persisted.append(run_id) or True,
    )
    assert result == {"engine": "hermes-agent", "content": "Task completed safely."}
    assert persisted == ["run_native_123"]
    assert calls[0][1] == "http://hermes:8642/v1/runs"
    assert calls[0][2]["headers"]["Authorization"] == "Bearer test-only-token"
    assert calls[0][2]["headers"]["Idempotency-Key"] == "suly-test-run-0001"
    assert calls[0][2]["json"] == {"input": "Do a safe task"}
    assert calls[1][1] == "http://hermes:8642/v1/runs/run_native_123"


@pytest.mark.parametrize("prompt", ["", "  ", "x" * 20001, None])
def test_hermes_bridge_rejects_invalid_prompt(monkeypatch, prompt):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="prompt"):
        hermes_agent.run_agent_turn(
            prompt,
            idempotency_key="test-key",
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
