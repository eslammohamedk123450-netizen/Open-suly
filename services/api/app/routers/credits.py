"""واجهة قراءة رصيد المستخدم وسجل الحركات؛ لا تسمح بأي تعديل أو تشغيل محرك."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.core.ratelimit import apply_rate_limit
from app.core.supabase import get_supabase_client

router = APIRouter(prefix="/v1/credits", tags=["credits"])
_bearer = HTTPBearer(auto_error=False)

_ACCOUNT_COLUMNS = "available_credits,reserved_credits,updated_at"
_RESERVATION_COLUMNS = (
    "id,engine_id,reserved_credits,settled_credits,status,expires_at,created_at,completed_at"
)
_LEDGER_COLUMNS = "id,reservation_id,transaction_type,available_delta,reserved_delta,engine_id,created_at"


def get_credit_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Client:
    """أنشئ عميلًا مرتبطًا بتوكن المستخدم لتطبيق RLS بدل استخدام service role."""
    if not get_settings().engine_credits_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Credit ledger is disabled on this server.",
        )
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
            detail="Credit ledger is not configured.",
        )
    return client


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None) or []
    if isinstance(data, dict):
        return [data]
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _integer(value: Any, code: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(code)
    if minimum is not None and value < minimum:
        raise RuntimeError(code)
    return value


def _optional_text(value: Any, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(code)
    return value


def _account(row: dict[str, Any] | None) -> dict[str, Any]:
    """حوّل الحساب إلى projection محدود، أو رصيد صفر قبل إنشاء الحساب."""
    if row is None:
        return {"available_credits": 0, "reserved_credits": 0, "updated_at": None}
    return {
        "available_credits": _integer(row.get("available_credits"), "credit_account_invalid", minimum=0),
        "reserved_credits": _integer(row.get("reserved_credits"), "credit_account_invalid", minimum=0),
        "updated_at": _optional_text(row.get("updated_at"), "credit_account_invalid"),
    }


def _reservation(row: dict[str, Any]) -> dict[str, Any]:
    status_value = row.get("status")
    if status_value not in {"reserved", "settled", "released"}:
        raise RuntimeError("credit_reservation_invalid")
    settled = row.get("settled_credits")
    if settled is not None:
        settled = _integer(settled, "credit_reservation_invalid", minimum=0)
    return {
        "id": _optional_text(row.get("id"), "credit_reservation_invalid"),
        "engine_id": _optional_text(row.get("engine_id"), "credit_reservation_invalid"),
        "reserved_credits": _integer(row.get("reserved_credits"), "credit_reservation_invalid", minimum=1),
        "settled_credits": settled,
        "status": status_value,
        "expires_at": _optional_text(row.get("expires_at"), "credit_reservation_invalid"),
        "created_at": _optional_text(row.get("created_at"), "credit_reservation_invalid"),
        "completed_at": _optional_text(row.get("completed_at"), "credit_reservation_invalid"),
    }


def _transaction(row: dict[str, Any]) -> dict[str, Any]:
    """لا نعيد metadata أو تفاصيل المهمة؛ نعرض فروق الرصيد فقط."""
    transaction_type = row.get("transaction_type")
    if transaction_type not in {"grant", "reserve", "settle", "release", "expire"}:
        raise RuntimeError("credit_transaction_invalid")
    return {
        "id": _optional_text(row.get("id"), "credit_transaction_invalid"),
        "reservation_id": _optional_text(row.get("reservation_id"), "credit_transaction_invalid"),
        "transaction_type": transaction_type,
        "available_delta": _integer(row.get("available_delta"), "credit_transaction_invalid"),
        "reserved_delta": _integer(row.get("reserved_delta"), "credit_transaction_invalid"),
        "engine_id": _optional_text(row.get("engine_id"), "credit_transaction_invalid"),
        "created_at": _optional_text(row.get("created_at"), "credit_transaction_invalid"),
    }


@router.get("")
def read_credit_summary(
    user: AuthenticatedUser = Depends(get_current_user),
    client: Client = Depends(get_credit_client),
) -> dict[str, Any]:
    """أعد ملخصًا للقراءة فقط؛ لا ينشئ حسابًا أو يمنح credits."""
    if not get_settings().engine_credits_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Credit ledger is disabled on this server.",
        )
    apply_rate_limit(f"credits:{user.id}", capacity=30, refill_seconds=60.0)
    try:
        with client:
            account_rows = _rows(
                client.table("credit_accounts")
                .select(_ACCOUNT_COLUMNS)
                .eq("user_id", user.id)
                .limit(1)
                .execute()
            )
            reservation_rows = _rows(
                client.table("credit_reservations")
                .select(_RESERVATION_COLUMNS)
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(25)
                .execute()
            )
            ledger_rows = _rows(
                client.table("credit_ledger")
                .select(_LEDGER_COLUMNS)
                .eq("user_id", user.id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
        return {
            "account": _account(account_rows[0] if account_rows else None),
            "reservations": [_reservation(row) for row in reservation_rows],
            "transactions": [_transaction(row) for row in ledger_rows],
        }
    except HTTPException:
        raise
    except Exception as exc:
        # لا نعرض تفاصيل PostgREST أو أسماء الجداول أو metadata للمستخدم.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Credit ledger is unavailable. Verify its migration and server flag.",
        ) from exc
