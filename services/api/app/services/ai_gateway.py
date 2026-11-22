import asyncio
import json
from typing import Any, Callable

import httpx

from app.core.config import get_settings


_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "openai-compatible": {
        "protocol": "openai-chat-completions",
        "streaming": True,
        "token_usage": True,
        "requires_api_key": True,
        "supports_cancellation": True,
    },
    "ollama": {
        "protocol": "ollama-chat",
        "streaming": True,
        "token_usage": True,
        "requires_api_key": False,
        "supports_cancellation": True,
    },
}


def provider_capabilities(provider: str | None = None) -> dict[str, Any]:
    """Return safe protocol capabilities without exposing provider credentials or URLs."""
    if provider is not None:
        capabilities = _PROVIDER_REGISTRY.get(provider)
        return {"provider": provider, **capabilities} if capabilities else {"provider": provider, "supported": False}
    return {
        name: {"provider": name, "supported": True, **capabilities}
        for name, capabilities in _PROVIDER_REGISTRY.items()
    }


def selected_model_profile() -> dict[str, Any]:
    """Describe only the server-selected model; do not imply remote model discovery."""
    settings = get_settings()
    configured = bool(settings.ai_provider in _PROVIDER_REGISTRY and settings.ai_model)
    capabilities = provider_capabilities(settings.ai_provider)
    return {
        "configured": configured,
        "provider": settings.ai_provider if configured else None,
        "model": settings.ai_model if configured else None,
        "max_output_tokens": settings.ai_max_output_tokens if configured else None,
        "capabilities": capabilities if configured else {},
        "discovery": "server_configured_selection_only",
    }


def model_registry() -> dict[str, Any]:
    """Return a registry containing only the model explicitly selected by the operator."""
    profile = selected_model_profile()
    if not profile["configured"]:
        return {"items": [], "discovery": "server_configured_selection_only"}
    return {
        "items": [{
            "id": profile["model"],
            "provider": profile["provider"],
            "max_output_tokens": profile["max_output_tokens"],
            "capabilities": profile["capabilities"],
        }],
        "discovery": "server_configured_selection_only",
    }


class AIProviderNotConfigured(RuntimeError):
    """Raised when no deliberate AI provider configuration is present."""


class AIProviderError(RuntimeError):
    """Raised when the configured provider cannot return a valid response."""


class AIProviderTimeout(RuntimeError):
    """Raised when the provider exceeds the configured timeout."""


_ALLOWED_ROLES = {"system", "user", "assistant"}
_MAX_MESSAGES = 40
_MAX_INPUT_CHARS = 48000
_MAX_REPLY_CHARS = 60000


def _provider_usage(body: Any, *, is_ollama: bool) -> dict[str, int] | None:
    """Extract only bounded token counts; do not estimate or derive monetary cost."""
    if not isinstance(body, dict):
        return None
    raw_usage = body.get("usage")
    if is_ollama:
        input_value = body.get("prompt_eval_count")
        output_value = body.get("eval_count")
    else:
        if not isinstance(raw_usage, dict):
            return None
        input_value = raw_usage.get("prompt_tokens")
        output_value = raw_usage.get("completion_tokens")
    for value in (input_value, output_value):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
            return None
    return {
        "input_tokens": input_value,
        "output_tokens": output_value,
        "total_tokens": input_value + output_value,
    }


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if not isinstance(messages, list) or not 1 <= len(messages) <= _MAX_MESSAGES:
        raise AIProviderError("The conversation context is outside the supported limits.")
    total_chars = 0
    for message in messages:
        if not isinstance(message, dict):
            raise AIProviderError("The conversation context contains an invalid message.")
        role = message.get("role")
        content = message.get("content")
        if role not in _ALLOWED_ROLES or not isinstance(content, str) or not content.strip():
            raise AIProviderError("The conversation context contains an invalid message.")
        total_chars += len(content)
        if total_chars > _MAX_INPUT_CHARS:
            raise AIProviderError("The conversation context is too large.")


async def generate_reply(
    messages: list[dict[str, str]],
    *,
    client: httpx.AsyncClient | None = None,
    on_usage: Callable[[dict[str, int]], None] | None = None,
) -> str:
    settings = get_settings()
    provider = settings.ai_provider
    if (
        provider not in {"openai-compatible", "ollama"}
        or not settings.ai_base_url
        or not settings.ai_model
        or (provider == "openai-compatible" and not settings.ai_api_key)
    ):
        raise AIProviderNotConfigured("No AI provider is configured.")

    _validate_messages(messages)
    is_ollama = provider == "ollama"
    url = (
        f"{settings.ai_base_url.rstrip('/')}/api/chat"
        if is_ollama
        else f"{settings.ai_base_url.rstrip('/')}/chat/completions"
    )
    payload: dict[str, Any] = (
        {
            "model": settings.ai_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": settings.ai_max_output_tokens},
        }
        if is_ollama
        else {
            "model": settings.ai_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": settings.ai_max_output_tokens,
            "stream": False,
        }
    )
    headers = {"Content-Type": "application/json"}
    if not is_ollama and settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key.get_secret_value()}"

    async def send(session: httpx.AsyncClient) -> str:
        response = await session.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.ai_timeout_seconds,
        )
        response.raise_for_status()
        try:
            body = response.json()
            content = (
                body["message"]["content"]
                if is_ollama
                else body["choices"][0]["message"]["content"]
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("The AI provider returned an invalid response.") from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("The AI provider returned an empty response.")
        content = content.strip()
        if len(content) > _MAX_REPLY_CHARS:
            raise AIProviderError("The AI provider response exceeded the supported limit.")
        if on_usage is not None:
            usage_summary = _provider_usage(body, is_ollama=is_ollama)
            if usage_summary is not None:
                # فشل تسجيل usage لا ينبغي أن يمنع وصول الرد النصي للمستخدم.
                try:
                    on_usage(usage_summary)
                except Exception:
                    pass
        return content

    async def send_with_safe_retry(session: httpx.AsyncClient) -> str:
        # Retry only connection-establishment failures: a read timeout may mean
        # the provider already processed and billed the request.
        for attempt in range(2):
            try:
                return await send(session)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt == 1:
                    raise
                await asyncio.sleep(0.15)
        raise AIProviderError("The AI provider could not be reached.")

    try:
        if client is not None:
            return await send_with_safe_retry(client)
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as session:
            return await send_with_safe_retry(session)
    except httpx.TimeoutException as exc:
        raise AIProviderTimeout("The AI provider timed out.") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            raise AIProviderError("The AI provider is rate-limiting requests. Try again shortly.") from exc
        raise AIProviderError(f"The AI provider returned HTTP {status_code}.") from exc
    except httpx.RequestError as exc:
        raise AIProviderError("The AI provider could not be reached.") from exc



async def stream_reply(
    messages: list[dict[str, str]],
    *,
    client: httpx.AsyncClient | None = None,
    on_usage: Callable[[dict[str, int]], None] | None = None,
):
    """Yield bounded text deltas from OpenAI-compatible SSE or Ollama NDJSON.

    Streaming deliberately has no automatic retry: once bytes have reached the
    caller, retrying could duplicate or reorder visible output. The caller owns
    persistence of the assembled final response.
    """
    settings = get_settings()
    provider = settings.ai_provider
    if (
        provider not in {"openai-compatible", "ollama"}
        or not settings.ai_base_url
        or not settings.ai_model
        or (provider == "openai-compatible" and not settings.ai_api_key)
    ):
        raise AIProviderNotConfigured("No AI provider is configured.")

    _validate_messages(messages)
    is_ollama = provider == "ollama"
    url = (
        f"{settings.ai_base_url.rstrip('/')}/api/chat"
        if is_ollama
        else f"{settings.ai_base_url.rstrip('/')}/chat/completions"
    )
    payload: dict[str, Any] = (
        {
            "model": settings.ai_model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.3, "num_predict": settings.ai_max_output_tokens},
        }
        if is_ollama
        else {
            "model": settings.ai_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": settings.ai_max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    )
    headers = {"Content-Type": "application/json"}
    if not is_ollama and settings.ai_api_key:
        headers["Authorization"] = f"Bearer {settings.ai_api_key.get_secret_value()}"

    async def consume(session: httpx.AsyncClient):
        total_chars = 0
        async with session.stream(
            "POST", url, headers=headers, json=payload,
            timeout=settings.ai_timeout_seconds,
        ) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line:
                    continue
                if is_ollama:
                    encoded = line
                else:
                    if not line.startswith("data:"):
                        continue
                    encoded = line[5:].strip()
                    if encoded == "[DONE]":
                        break
                try:
                    body = json.loads(encoded)
                except (ValueError, TypeError) as exc:
                    raise AIProviderError("The AI provider returned an invalid stream event.") from exc
                if not isinstance(body, dict):
                    raise AIProviderError("The AI provider returned an invalid stream event.")
                if on_usage is not None:
                    usage = _provider_usage(body, is_ollama=is_ollama)
                    if usage is not None:
                        try:
                            on_usage(usage)
                        except Exception:
                            pass

                if is_ollama:
                    message = body.get("message") or {}
                    fragment = message.get("content", "") if isinstance(message, dict) else ""
                else:
                    choices = body.get("choices")
                    fragment = ""
                    if isinstance(choices, list) and choices:
                        delta = (choices[0] or {}).get("delta") or {}
                        fragment = delta.get("content", "")
                        if isinstance(fragment, list):
                            fragment = "".join(
                                part.get("text", "") for part in fragment
                                if isinstance(part, dict) and part.get("type") == "text"
                            )
                if fragment:
                    if not isinstance(fragment, str):
                        raise AIProviderError("The AI provider returned an invalid stream fragment.")
                    total_chars += len(fragment)
                    if total_chars > _MAX_REPLY_CHARS:
                        raise AIProviderError("The AI provider response exceeded the supported limit.")
                    yield fragment
                if is_ollama and body.get("done") is True:
                    break

    try:
        if client is not None:
            async for fragment in consume(client):
                yield fragment
        else:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as session:
                async for fragment in consume(session):
                    yield fragment
    except httpx.TimeoutException as exc:
        raise AIProviderTimeout("The AI provider timed out.") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise AIProviderError("The AI provider is rate-limiting requests. Try again shortly.") from exc
        raise AIProviderError(f"The AI provider returned HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise AIProviderError("The AI provider could not be reached.") from exc
