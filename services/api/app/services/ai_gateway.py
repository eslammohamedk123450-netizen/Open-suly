from typing import Any

import httpx

from app.core.config import get_settings


class AIProviderNotConfigured(RuntimeError):
    """Raised when no deliberate AI provider configuration is present."""


class AIProviderError(RuntimeError):
    """Raised when the configured provider cannot return a valid response."""


class AIProviderTimeout(RuntimeError):
    """Raised when the provider exceeds the configured timeout."""


async def generate_reply(
    messages: list[dict[str, str]],
    *,
    client: httpx.AsyncClient | None = None,
) -> str:
    settings = get_settings()
    if (
        settings.ai_provider != "openai-compatible"
        or not settings.ai_base_url
        or not settings.ai_api_key
        or not settings.ai_model
    ):
        raise AIProviderNotConfigured("No AI provider is configured.")

    url = f"{settings.ai_base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": settings.ai_max_output_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }

    async def send(session: httpx.AsyncClient) -> str:
        response = await session.post(url, headers=headers, json=payload)
        response.raise_for_status()
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
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
        return content.strip()

    if client is not None:
        try:
            return await send(client)
        except httpx.TimeoutException as exc:
            raise AIProviderTimeout("The AI provider timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(f"The AI provider returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            raise AIProviderError("The AI provider could not be reached.") from exc

    try:
        async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as session:
            return await send(session)
    except httpx.TimeoutException as exc:
        raise AIProviderTimeout("The AI provider timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise AIProviderError(f"The AI provider returned HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise AIProviderError("The AI provider could not be reached.") from exc
