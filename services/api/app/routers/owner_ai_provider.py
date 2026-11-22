"""Owner-only API for the centralized AI provider configuration."""
from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.supabase import get_supabase_admin_client
from app.services.ai_provider_config import (
    AIProviderConfigurationUnavailable,
    read_ai_provider_config,
    store_ai_provider_config,
    clear_ai_provider_config,
)

router = APIRouter(prefix="/v1/owner/ai-provider", tags=["owner-ai-provider"])


class AIProviderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai-compatible"] = "openai-compatible"
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    api_key: SecretStr

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use a public HTTPS provider base URL without credentials, query, or fragment.")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
            raise ValueError("Local provider URLs are not supported in the owner key form.")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Provider URL must not target a private or reserved IP address.")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Model identifier is invalid.")
        return value

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret or len(secret) > 4096:
            raise ValueError("API key must contain 1–4096 characters.")
        return SecretStr(secret)


class AIProviderStatus(BaseModel):
    configured: bool
    source: Literal["vault", "environment", "none"]
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key_set: bool


def require_app_owner(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Authorize only the server-configured, email-verified SULY owner."""
    configured_email = get_settings().suly_owner_email
    if not configured_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="إعداد بريد مالك التطبيق غير مكتمل على الخادم.",
        )
    if (
        not user.email
        or not user.email_verified
        or user.email.strip().casefold() != configured_email.strip().casefold()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة متاحة لمالك التطبيق فقط.",
        )
    return user


def _admin_client():
    admin = get_supabase_admin_client()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="إعداد اتصال الخادم بـ Supabase غير مكتمل.",
        )
    return admin


def _environment_status() -> AIProviderStatus:
    """اعرض حالة إعداد الخادم دون كشف المفتاح الاحتياطي."""
    settings = get_settings()
    if (
        settings.ai_provider == "openai-compatible"
        and settings.ai_base_url
        and settings.ai_model
        and settings.ai_api_key
    ):
        return AIProviderStatus(
            configured=True,
            source="environment",
            provider=settings.ai_provider,
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            api_key_set=True,
        )
    return AIProviderStatus(configured=False, source="none", api_key_set=False)


def _status_from_config(config: dict, source: Literal["vault", "environment"]) -> AIProviderStatus:
    return AIProviderStatus(
        configured=True,
        source=source,
        provider=config["provider"],
        base_url=config["base_url"],
        model=config["model"],
        api_key_set=True,
    )


@router.get("", response_model=AIProviderStatus)
def get_ai_provider_status(
    _owner: AuthenticatedUser = Depends(require_app_owner),
) -> AIProviderStatus:
    admin = _admin_client()
    try:
        with admin:
            config = read_ai_provider_config(admin)
        if config is not None:
            return _status_from_config(config, "vault")
    except AIProviderConfigurationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تعذر قراءة إعدادات مزود AI الآمنة حاليًا.",
        ) from exc

    return _environment_status()


@router.put("", response_model=AIProviderStatus)
def update_ai_provider_config(
    request: AIProviderUpdateRequest,
    _owner: AuthenticatedUser = Depends(require_app_owner),
    _rate_limit: None = Depends(rate_limit("owner_ai_provider")),
) -> AIProviderStatus:
    admin = _admin_client()
    try:
        with admin:
            store_ai_provider_config(
                admin,
                base_url=request.base_url,
                model=request.model,
                api_key=request.api_key.get_secret_value(),
            )
    except AIProviderConfigurationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تعذر حفظ إعداد مزود AI في Supabase Vault.",
        ) from exc
    return AIProviderStatus(
        configured=True,
        source="vault",
        provider=request.provider,
        base_url=request.base_url,
        model=request.model,
        api_key_set=True,
    )



@router.delete("", response_model=AIProviderStatus)
def clear_ai_provider_config_for_owner(
    _owner: AuthenticatedUser = Depends(require_app_owner),
    _rate_limit: None = Depends(rate_limit("owner_ai_provider")),
) -> AIProviderStatus:
    """احذف سر Vault فقط، مع إبقاء إعداد الخادم الاحتياطي واضحًا إن وُجد."""
    admin = _admin_client()
    try:
        with admin:
            clear_ai_provider_config(admin)
            # اقرأ بعد الحذف؛ إذا سبق طلبًا متزامنًا وأعاد إعدادًا جديدًا فلا نعرض حالة مضللة.
            config = read_ai_provider_config(admin)
        if config is not None:
            return _status_from_config(config, "vault")
    except AIProviderConfigurationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تعذر حذف إعداد مزود AI من Supabase Vault بأمان.",
        ) from exc
    return _environment_status()
