from typing import Any

import httpx

from app.core.config import get_settings


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
        return content

    try:
        if client is not None:
            return await send(client)
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as session:
            return await send(session)
    except httpx.TimeoutException as exc:
        raise AIProviderTimeout("The AI provider timed out.") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            raise AIProviderError("The AI provider is rate-limiting requests. Try again shortly.") from exc
        raise AIProviderError(f"The AI provider returned HTTP {status_code}.") from exc
    except httpx.RequestError as exc:
        raise AIProviderError("The AI provider could not be reached.") from exc
