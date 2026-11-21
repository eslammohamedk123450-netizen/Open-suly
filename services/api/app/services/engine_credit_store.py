"""Server-only, validated adapter for SULY engine credit ledger RPCs."""
from __future__ import annotations

import re
from uuid import UUID

from supabase import Client

_ENGINE_IDS = frozenset({"hermes-agent", "opencode"})
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_./-]{7,127}$")
_REASON = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_MAX_CREDITS = 1_000_000


def _canonical_uuid(value: str, code: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(code) from exc
    if str(parsed) != value:
        raise ValueError(code)
    return value


def _credits(value: int, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= _MAX_CREDITS:
        raise ValueError("engine_credit_amount_invalid")
    return value


def _idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_KEY.fullmatch(value):
        raise ValueError("engine_credit_idempotency_key_invalid")
    return value


def _rpc_value(response, function_name: str):
    value = response.data
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get(function_name)
    return value


class EngineCreditStore:
    """واجهة RPC ضيقة؛ لا تمنح أي رصيد أو تخصم منه عبر table CRUD مباشر."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def grant(self, *, user_id: str, amount: int, reason: str, idempotency_key: str) -> int:
        owner = _canonical_uuid(user_id, "engine_credit_user_invalid")
        value = _credits(amount)
        if not isinstance(reason, str) or not _REASON.fullmatch(reason):
            raise ValueError("engine_credit_reason_invalid")
        key = _idempotency_key(idempotency_key)
        response = self._client.rpc("grant_engine_credits", {
            "p_user_id": owner, "p_amount": value, "p_reason": reason,
            "p_idempotency_key": key,
        }).execute()
        result = _rpc_value(response, "grant_engine_credits")
        if isinstance(result, bool) or not isinstance(result, int) or result < 0:
            raise RuntimeError("engine_credit_grant_invalid_response")
        return result

    def reserve(
        self, *, user_id: str, task_id: str, engine_run_id: str,
        engine_id: str, amount: int, idempotency_key: str,
    ) -> UUID:
        owner = _canonical_uuid(user_id, "engine_credit_user_invalid")
        task = _canonical_uuid(task_id, "engine_credit_task_invalid")
        run = _canonical_uuid(engine_run_id, "engine_credit_run_invalid")
        if engine_id not in _ENGINE_IDS:
            raise ValueError("engine_credit_engine_invalid")
        value = _credits(amount)
        key = _idempotency_key(idempotency_key)
        response = self._client.rpc("reserve_engine_credits", {
            "p_user_id": owner, "p_task_id": task, "p_engine_run_id": run,
            "p_engine_id": engine_id, "p_amount": value, "p_idempotency_key": key,
        }).execute()
        result = _rpc_value(response, "reserve_engine_credits")
        try:
            reservation_id = UUID(str(result))
        except (TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("engine_credit_reserve_invalid_response") from exc
        if str(reservation_id) != str(result):
            raise RuntimeError("engine_credit_reserve_invalid_response")
        return reservation_id

    def settle(
        self, *, user_id: str, reservation_id: str,
        actual_credits: int, idempotency_key: str,
    ) -> bool:
        owner = _canonical_uuid(user_id, "engine_credit_user_invalid")
        reservation = _canonical_uuid(reservation_id, "engine_credit_reservation_invalid")
        actual = _credits(actual_credits, allow_zero=True)
        key = _idempotency_key(idempotency_key)
        response = self._client.rpc("settle_engine_credits", {
            "p_user_id": owner, "p_reservation_id": reservation,
            "p_actual_credits": actual, "p_idempotency_key": key,
        }).execute()
        result = _rpc_value(response, "settle_engine_credits")
        if not isinstance(result, bool):
            raise RuntimeError("engine_credit_settle_invalid_response")
        return result

    def release(
        self, *, user_id: str, reservation_id: str,
        reason: str, idempotency_key: str,
    ) -> bool:
        owner = _canonical_uuid(user_id, "engine_credit_user_invalid")
        reservation = _canonical_uuid(reservation_id, "engine_credit_reservation_invalid")
        if not isinstance(reason, str) or not _REASON.fullmatch(reason):
            raise ValueError("engine_credit_reason_invalid")
        key = _idempotency_key(idempotency_key)
        response = self._client.rpc("release_engine_credits", {
            "p_user_id": owner, "p_reservation_id": reservation,
            "p_reason": reason, "p_idempotency_key": key,
        }).execute()
        result = _rpc_value(response, "release_engine_credits")
        if not isinstance(result, bool):
            raise RuntimeError("engine_credit_release_invalid_response")
        return result

    def release_expired(self, batch_size: int = 25) -> int:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
            raise ValueError("engine_credit_expiry_batch_invalid")
        response = self._client.rpc(
            "release_expired_engine_credit_reservations", {"p_batch_size": batch_size}
        ).execute()
        result = _rpc_value(response, "release_expired_engine_credit_reservations")
        if isinstance(result, bool) or not isinstance(result, int) or not 0 <= result <= batch_size:
            raise RuntimeError("engine_credit_expiry_invalid_response")
        return result
