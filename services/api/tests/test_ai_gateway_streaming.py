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
