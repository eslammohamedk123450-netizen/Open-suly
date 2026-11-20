"""Narrow HTTP bridge to the isolated Hermes Agent API server.

The bridge is deliberately disabled by default. Hermes' API server exposes its
full agent toolset, including terminal execution; enabling this adapter is only
safe after the Hermes container's sandbox and tool policy have been reviewed.
SULY never sends Supabase credentials or trusted approval scopes to Hermes.
"""
from __future__ import annotations

import asyncio
from threading import Event

import httpx
from urllib.parse import urlsplit

from app.core.config import get_settings


class HermesAgentUnavailable(RuntimeError):
    """Raised when the optional Hermes runtime is not safely configured."""


class HermesAgentError(RuntimeError):
    """Raised for bounded, non-sensitive upstream failures."""


class HermesAgentCancelled(RuntimeError):
    """Raised when SULY cancels the in-flight HTTP request."""


def run_agent_turn(
    prompt: str,
    *,
    timeout_seconds: float | None = None,
    cancel_event: Event | None = None,
) -> dict[str, str]:
    settings = get_settings()
    if not settings.hermes_agent_enabled:
        raise HermesAgentUnavailable("Hermes agent runtime is disabled.")
    if not settings.hermes_agent_base_url or not settings.hermes_agent_api_key:
        raise HermesAgentUnavailable("Hermes agent runtime is not configured.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise ValueError("Hermes prompt must contain 1–20000 characters.")

    base_url = settings.hermes_agent_base_url.rstrip("/")
    parsed_base = urlsplit(base_url)
    if (
        parsed_base.scheme not in {"http", "https"}
        or not parsed_base.hostname
        or parsed_base.username is not None
        or parsed_base.password is not None
        or parsed_base.query
        or parsed_base.fragment
    ):
        raise HermesAgentUnavailable("Hermes agent base URL is invalid.")
    url = f"{base_url}/v1/chat/completions"
    token = settings.hermes_agent_api_key.get_secret_value()
    timeout = timeout_seconds if timeout_seconds is not None else settings.hermes_agent_timeout_seconds
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 300:
        raise ValueError("Hermes request timeout is outside the allowed range.")
    if cancel_event is not None and cancel_event.is_set():
        raise HermesAgentCancelled("Hermes request was cancelled.")

    async def request() -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                request_task = asyncio.create_task(client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "model": settings.hermes_agent_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                    },
                ))
                if cancel_event is not None:
                    async def watch_cancellation() -> None:
                        while not cancel_event.is_set():
                            await asyncio.sleep(0.05)

                    cancel_task = asyncio.create_task(watch_cancellation())
                    done, _ = await asyncio.wait(
                        {request_task, cancel_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancel_task in done:
                        request_task.cancel()
                        await asyncio.gather(request_task, return_exceptions=True)
                        raise HermesAgentCancelled("Hermes request was cancelled.")
                    cancel_task.cancel()
                    await asyncio.gather(cancel_task, return_exceptions=True)
                response = await request_task
                response.raise_for_status()
                payload = response.json()
        except HermesAgentCancelled:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            # Do not propagate upstream bodies, which may contain prompts or secrets.
            raise HermesAgentError("Hermes agent request failed.") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HermesAgentError("Hermes agent returned an invalid response.") from exc
        if not isinstance(content, str) or not content.strip():
            raise HermesAgentError("Hermes agent returned an empty response.")
        if len(content) > settings.hermes_agent_max_output_chars:
            raise HermesAgentError("Hermes agent response exceeded the configured limit.")
        return {"engine": "hermes-agent", "content": content}

    return asyncio.run(request())
