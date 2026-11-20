from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.services import hermes_agent


def settings(**overrides):
    values = {
        "hermes_agent_enabled": True,
        "hermes_agent_base_url": "http://hermes:8642",
        "hermes_agent_api_key": SecretStr("test-only-token"),
        "hermes_agent_model": "hermes-agent",
        "hermes_agent_timeout_seconds": 90.0,
        "hermes_agent_max_output_chars": 12000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_hermes_bridge_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings(hermes_agent_enabled=False))
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="disabled"):
        hermes_agent.run_agent_turn("hello")


def test_hermes_bridge_requires_url_and_key(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_api_key=None),
    )
    with pytest.raises(hermes_agent.HermesAgentUnavailable, match="not configured"):
        hermes_agent.run_agent_turn("hello")


def test_hermes_bridge_sends_only_bounded_user_prompt(monkeypatch):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Task completed."}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(hermes_agent.httpx, "post", fake_post)
    result = hermes_agent.run_agent_turn("Do a safe task")

    assert result == {"engine": "hermes-agent", "content": "Task completed."}
    assert captured["url"] == "http://hermes:8642/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-only-token"
    assert captured["json"]["messages"] == [{"role": "user", "content": "Do a safe task"}]
    assert captured["json"]["stream"] is False
    assert captured["timeout"] == 90.0


@pytest.mark.parametrize("prompt", ["", "  ", "x" * 20001, None])
def test_hermes_bridge_rejects_invalid_prompt(monkeypatch, prompt):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())
    with pytest.raises(ValueError, match="prompt"):
        hermes_agent.run_agent_turn(prompt)


def test_hermes_bridge_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(
        hermes_agent, "get_settings",
        lambda: settings(hermes_agent_max_output_chars=256),
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "x" * 257}}]}

    monkeypatch.setattr(hermes_agent.httpx, "post", lambda *_args, **_kwargs: Response())
    with pytest.raises(hermes_agent.HermesAgentError, match="exceeded"):
        hermes_agent.run_agent_turn("hello")


def test_hermes_bridge_redacts_upstream_http_error(monkeypatch):
    monkeypatch.setattr(hermes_agent, "get_settings", lambda: settings())

    def fail(*_args, **_kwargs):
        raise hermes_agent.httpx.ConnectError("sensitive upstream response body")

    monkeypatch.setattr(hermes_agent.httpx, "post", fail)
    with pytest.raises(hermes_agent.HermesAgentError, match="request failed") as error:
        hermes_agent.run_agent_turn("hello")
    assert "sensitive upstream response body" not in str(error.value)
