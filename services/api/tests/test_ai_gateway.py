import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services import ai_gateway


def configured_settings() -> Settings:
    return Settings(
        ai_provider="openai-compatible",
        ai_base_url="https://provider.example/v1",
        ai_api_key=SecretStr("server-test-secret"),
        ai_model="test-model",
        ai_timeout_seconds=7,
    )


def test_gateway_stays_disabled_without_provider_configuration(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: Settings(ai_provider="disabled"))
    with pytest.raises(ai_gateway.AIProviderNotConfigured):
        asyncio.run(ai_gateway.generate_reply([{"role": "user", "content": "hello"}]))


def test_gateway_calls_openai_compatible_endpoint_without_leaking_key(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization", "")
        seen["model"] = json.loads(request.content)["model"]
        seen["timeout"] = str(request.extensions.get("timeout", {}).get("read"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "  SULY test reply  "}}]})

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ai_gateway.generate_reply([{"role": "user", "content": "hello"}], client=client)

    answer = asyncio.run(run())
    assert answer == "SULY test reply"
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["authorization"] == "Bearer server-test-secret"
    assert seen["model"] == "test-model"
    assert seen["timeout"] == "7.0"


@pytest.mark.parametrize("messages", [
    [],
    [{"role": "tool", "content": "not allowed"}],
    [{"role": "user", "content": "   "}],
    [{"role": "user", "content": "x"}] * 41,
])
def test_gateway_rejects_invalid_context_before_network(monkeypatch, messages) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("network must not be called"))
        )) as client:
            await ai_gateway.generate_reply(messages, client=client)

    with pytest.raises(ai_gateway.AIProviderError):
        asyncio.run(run())


def test_gateway_rejects_oversized_context(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)
    messages = [{"role": "user", "content": "x" * 48001}]

    with pytest.raises(ai_gateway.AIProviderError, match="too large"):
        asyncio.run(ai_gateway.generate_reply(messages))


def test_gateway_maps_timeout_for_injected_client(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            await ai_gateway.generate_reply([{"role": "user", "content": "hello"}], client=client)

    with pytest.raises(ai_gateway.AIProviderTimeout):
        asyncio.run(run())


def test_gateway_maps_rate_limit_without_exposing_response_body(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, text="private provider detail")
        )) as client:
            await ai_gateway.generate_reply([{"role": "user", "content": "hello"}], client=client)

    with pytest.raises(ai_gateway.AIProviderError, match="rate-limiting") as error:
        asyncio.run(run())
    assert "private provider detail" not in str(error.value)


def test_gateway_rejects_malformed_and_oversized_replies(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", configured_settings)

    async def run(body: dict) -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=body)
        )) as client:
            await ai_gateway.generate_reply([{"role": "user", "content": "hello"}], client=client)

    with pytest.raises(ai_gateway.AIProviderError, match="invalid response"):
        asyncio.run(run({"choices": []}))
    with pytest.raises(ai_gateway.AIProviderError, match="exceeded"):
        asyncio.run(run({"choices": [{"message": {"content": "x" * 60001}}]}))

def test_gateway_supports_local_ollama_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: Settings(
        ai_provider="ollama",
        ai_base_url="http://ollama:11434",
        ai_model="qwen2.5:3b",
        ai_api_key=None,
        ai_timeout_seconds=12,
        ai_max_output_tokens=700,
    ))
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen2.5:3b",
            "message": {"role": "assistant", "content": "  إجابة محلية  "},
            "done": True,
        })

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ai_gateway.generate_reply(
                [{"role": "user", "content": "اشرح لي"}], client=client
            )

    assert asyncio.run(run()) == "إجابة محلية"
    assert seen["url"] == "http://ollama:11434/api/chat"
    assert seen["authorization"] is None
    body = seen["body"]
    assert body["model"] == "qwen2.5:3b"
    assert body["stream"] is False
    assert body["options"]["num_predict"] == 700


def test_gateway_rejects_ollama_malformed_response(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: Settings(
        ai_provider="ollama",
        ai_base_url="http://ollama:11434",
        ai_model="qwen2.5:3b",
    ))

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"message": {}})
        )) as client:
            await ai_gateway.generate_reply(
                [{"role": "user", "content": "hello"}], client=client
            )

    with pytest.raises(ai_gateway.AIProviderError, match="invalid response"):
        asyncio.run(run())

