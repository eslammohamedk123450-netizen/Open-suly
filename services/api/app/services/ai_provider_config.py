"""Server-only access to the owner-managed AI provider configuration in Vault."""
from __future__ import annotations

import json
from typing import Any

from pydantic import SecretStr

from app.core.config import Settings, get_settings


class AIProviderConfigurationUnavailable(RuntimeError):
    """Raised when the restricted Vault RPC cannot return a valid configuration."""


def read_ai_provider_config(admin: Any) -> dict[str, Any] | None:
    """Read the decrypted Vault value through a service-role-only database RPC."""
    rpc = getattr(admin, "rpc", None)
    if not callable(rpc):
        # Lightweight test doubles and older local setups may not expose RPC.
        return None
    try:
        response = rpc("suly_ai_provider_config_get", {}).execute()
        value = response.data
    except Exception as exc:
        raise AIProviderConfigurationUnavailable from exc

    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise AIProviderConfigurationUnavailable from exc
    if not isinstance(value, dict):
        raise AIProviderConfigurationUnavailable

    provider = value.get("provider")
    base_url = value.get("base_url")
    model = value.get("model")
    api_key = value.get("api_key")
    if (
        provider != "openai-compatible"
        or not isinstance(base_url, str)
        or not base_url.startswith("https://")
        or not isinstance(model, str)
        or not model.strip()
        or not isinstance(api_key, str)
        or not api_key.strip()
    ):
        raise AIProviderConfigurationUnavailable

    return {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": SecretStr(api_key),
    }


def store_ai_provider_config(
    admin: Any,
    *,
    base_url: str,
    model: str,
    api_key: str,
) -> None:
    """Encrypt and replace the config in Vault without returning its key."""
    try:
        admin.rpc(
            "suly_ai_provider_config_set",
            {
                "p_config": {
                    "provider": "openai-compatible",
                    "base_url": base_url.rstrip("/"),
                    "model": model,
                    "api_key": api_key,
                }
            },
        ).execute()
    except Exception as exc:
        raise AIProviderConfigurationUnavailable from exc


def clear_ai_provider_config(admin: Any) -> None:
    """احذف إعداد المزود من Vault عبر RPC مقيدة بدور الخادم فقط."""
    try:
        admin.rpc("suly_ai_provider_config_clear", {}).execute()
    except Exception as exc:
        raise AIProviderConfigurationUnavailable from exc


def ai_settings_from_config(config: dict[str, Any]) -> Settings:
    """Build request-scoped gateway settings from the decrypted server-only value."""
    limits = get_settings()
    return Settings(
        ai_provider=config["provider"],
        ai_base_url=config["base_url"],
        ai_api_key=config["api_key"],
        ai_model=config["model"],
        ai_timeout_seconds=limits.ai_timeout_seconds,
        ai_max_output_tokens=limits.ai_max_output_tokens,
    )
