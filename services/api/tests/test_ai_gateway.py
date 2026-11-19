import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services import ai_gateway


def test_gateway_stays_disabled_without_provider_configuration(monkeypatch) -> None:
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: Settings(ai_provider="disabled"))

    with pytest.raises(ai_gateway.AIProviderNotConfigured):
        asyncio.run(ai_gateway.generate_reply([{"role": "user", "content": "hello"}]))


def test_gateway_calls_openai_compatible_endpoint_without_leaking_key(monkeypatch) -> None:
    settings = Settings(
        ai_provider="openai-compatible",
        ai_base_url="https://provider.example/v1",
        ai_api_key=SecretStr("server-test-secret"),
        ai_model="test-model",
    )
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: settings)
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization", "")
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "  SULY test reply  "}}]})

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ai_gateway.generate_reply([{"role": "user", "content": "hello"}], client=client)

    answer = asyncio.run(run())

    assert answer == "SULY test reply"
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["authorization"] == "Bearer server-test-secret"
    assert seen["model"] == "test-model"
