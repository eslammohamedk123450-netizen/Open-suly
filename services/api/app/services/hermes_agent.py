"""Narrow HTTP bridge to the isolated Hermes Agent API server.

The bridge is deliberately disabled by default. Hermes' API server exposes its
full agent toolset, including terminal execution; enabling this adapter is only
safe after the Hermes container's sandbox and tool policy have been reviewed.
SULY never sends Supabase credentials or trusted approval scopes to Hermes.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings


class HermesAgentUnavailable(RuntimeError):
    """Raised when the optional Hermes runtime is not safely configured."""


class HermesAgentError(RuntimeError):
    """Raised for bounded, non-sensitive upstream failures."""


def run_agent_turn(prompt: str, *, timeout_seconds: float | None = None) -> dict[str, str]:
    settings = get_settings()
    if not settings.hermes_agent_enabled:
        raise HermesAgentUnavailable("Hermes agent runtime is disabled.")
    if not settings.hermes_agent_base_url or not settings.hermes_agent_api_key:
        raise HermesAgentUnavailable("Hermes agent runtime is not configured.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise ValueError("Hermes prompt must contain 1–20000 characters.")

    base_url = settings.hermes_agent_base_url.rstrip("/")
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        raise HermesAgentUnavailable("Hermes agent base URL must use HTTP or HTTPS.")
    url = f"{base_url}/v1/chat/completions"
    token = settings.hermes_agent_api_key.get_secret_value()
    timeout = timeout_seconds or settings.hermes_agent_timeout_seconds
    if not 1 <= timeout <= 300:
        raise ValueError("Hermes request timeout is outside the allowed range.")

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": settings.hermes_agent_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
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
