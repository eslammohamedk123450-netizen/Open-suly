"""Read-only, owner-scoped summary of provider-reported chat token usage."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.ratelimit import apply_rate_limit
from app.core.supabase import get_supabase_client


router = APIRouter(prefix="/v1/usage", tags=["usage"])
_bearer = HTTPBearer(auto_error=False)
_MAX_MESSAGES = 500
_FETCH_LIMIT = _MAX_MESSAGES + 1
_MAX_TOKEN_COUNT = 1_000_000_000


def get_chat_usage_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Any:
    """Use the authenticated user's JWT and RLS, never the service-role client."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    client = get_supabase_client(credentials.credentials)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat usage is not configured.",
        )
    return client


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    if isinstance(data, dict):
        return [data]
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _usage_counts(metadata: Any) -> tuple[int, int] | None:
    """Validate provider counts; malformed or missing telemetry is ignored."""
    if not isinstance(metadata, dict):
        return None
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    for value in (input_tokens, output_tokens):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= _MAX_TOKEN_COUNT
        ):
            return None
    return input_tokens, output_tokens


def _safe_timestamp(value: Any) -> str | None:
    """Keep only a small timestamp string; never expose other metadata fields."""
    return value if isinstance(value, str) and len(value) <= 64 else None


@router.get("/chat")
def read_chat_usage(
    user: AuthenticatedUser = Depends(get_current_user),
    client: Any = Depends(get_chat_usage_client),
) -> dict[str, Any]:
    """Summarize at most the newest 500 assistant messages for this account."""
    apply_rate_limit(f"chat_usage:{user.id}", capacity=20, refill_seconds=60.0)
    try:
        with client:
            rows = _rows(
                client.table("messages")
                .select("metadata,created_at")
                .eq("user_id", user.id)
                .eq("role", "assistant")
                .order("created_at", desc=True)
                .order("id", desc=True)
                .limit(_FETCH_LIMIT)
                .execute()
            )
        sampled = rows[:_MAX_MESSAGES]
        input_tokens = 0
        output_tokens = 0
        usage_records = 0
        for row in sampled:
            counts = _usage_counts(row.get("metadata"))
            if counts is None:
                continue
            usage_records += 1
            input_tokens += counts[0]
            output_tokens += counts[1]
        truncated = len(rows) > _MAX_MESSAGES
        timestamps = [_safe_timestamp(row.get("created_at")) for row in sampled]
        timestamps = [value for value in timestamps if value is not None]
        return {
            "scope": "chat",
            "coverage": "latest_500_assistant_messages" if truncated else "all_assistant_messages",
            "assistant_messages_checked": len(sampled),
            "usage_records": usage_records,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "truncated": truncated,
            "sample_limit": _MAX_MESSAGES,
            "period_start": timestamps[-1] if timestamps else None,
            "period_end": timestamps[0] if timestamps else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Metadata/DB diagnostics can contain private details; keep the API error generic.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat usage is temporarily unavailable.",
        ) from exc
