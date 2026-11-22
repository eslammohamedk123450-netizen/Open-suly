import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.services import ai_gateway


@pytest.mark.parametrize(
    ("provider", "body", "expected"),
    [
        (
            "openai-compatible",
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
            'data: [DONE]\n\n',
            ["Hello", " world"],
        ),
        (
            "ollama",
            '{"message":{"content":"مرحبا"},"done":false}\n'
            '{"message":{"content":" بك"},"done":true}\n',
            ["مرحبا", " بك"],
        ),
    ],
)
def test_stream_reply_yields_provider_deltas(monkeypatch, provider, body, expected):
    monkeypatch.setattr(
        ai_gateway,
        "get_settings",
        lambda: Settings(
            ai_provider=provider,
            ai_base_url="https://provider.example",
            ai_api_key="test-secret" if provider == "openai-compatible" else None,
            ai_model="test-model",
            ai_timeout_seconds=10,
            ai_max_output_tokens=128,
        ),
    )
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, text=body)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return [part async for part in ai_gateway.stream_reply(
                [{"role": "user", "content": "hello"}], client=client
            )]

    assert asyncio.run(run()) == expected
    assert captured["payload"]["stream"] is True
    if provider == "openai-compatible":
        assert captured["authorization"] == "Bearer test-secret"
    else:
        assert captured["authorization"] is None


def test_stream_reply_rejects_invalid_event(monkeypatch):
    monkeypatch.setattr(
        ai_gateway,
        "get_settings",
        lambda: Settings(
            ai_provider="openai-compatible",
            ai_base_url="https://provider.example",
            ai_api_key="test-secret",
            ai_model="test-model",
        ),
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, text="data: not-json\n\n")
        )) as client:
            return [part async for part in ai_gateway.stream_reply(
                [{"role": "user", "content": "hello"}], client=client
            )]

    with pytest.raises(ai_gateway.AIProviderError, match="invalid stream event"):
        asyncio.run(run())


def test_stream_reply_enforces_total_output_limit(monkeypatch):
    monkeypatch.setattr(
        ai_gateway,
        "get_settings",
        lambda: Settings(
            ai_provider="openai-compatible",
            ai_base_url="https://provider.example",
            ai_api_key="test-secret",
            ai_model="test-model",
        ),
    )
    oversized = "x" * 30001
    event = "data: " + json.dumps({"choices": [{"delta": {"content": oversized}}]}) + "\n\n"

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, text=event)
        )) as client:
            return [part async for part in ai_gateway.stream_reply(
                [{"role": "user", "content": "hello"}], client=client
            )]

    with pytest.raises(ai_gateway.AIProviderError, match="exceeded"):
        asyncio.run(run())



def test_provider_registry_reports_only_supported_capabilities(monkeypatch):
    monkeypatch.setattr(
        ai_gateway,
        "get_settings",
        lambda: Settings(
            ai_provider="ollama",
            ai_model="qwen2.5:3b",
            ai_max_output_tokens=512,
        ),
    )
    providers = ai_gateway.provider_capabilities()
    assert set(providers) == {"openai-compatible", "ollama"}
    assert providers["ollama"]["streaming"] is True
    assert providers["ollama"]["requires_api_key"] is False
    profile = ai_gateway.selected_model_profile()
    assert profile["configured"] is True
    assert profile["model"] == "qwen2.5:3b"
    assert profile["discovery"] == "server_configured_selection_only"
    assert "api_key" not in str(profile).lower()



def test_openai_stream_extracts_final_usage_event(monkeypatch):
    monkeypatch.setattr(
        ai_gateway,
        "get_settings",
        lambda: Settings(
            ai_provider="openai-compatible",
            ai_base_url="https://provider.example",
            ai_api_key="test-secret",
            ai_model="test-model",
        ),
    )
    usage = []
    stream = (
        'data: {"choices":[{"delta":{"content":"ok"}}]}\\n\\n'
        'data: {"choices":[],"usage":{"prompt_tokens":14,"completion_tokens":6,"total_tokens":20}}\\n\\n'
        'data: [DONE]\\n\\n'
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, text=stream)
        )) as client:
            return [part async for part in ai_gateway.stream_reply(
                [{"role": "user", "content": "hello"}],
                client=client,
                on_usage=usage.append,
            )]

    assert asyncio.run(run()) == ["ok"]
    assert usage == [{"input_tokens": 14, "output_tokens": 6, "total_tokens": 20}]
