"""Fail-closed protocol reducers for a future task-scoped OpenCode adapter.

This module does not perform HTTP requests or start OpenCode. It narrows the
upstream session/permission/event protocol before any adapter can expose it.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

_SESSION_ID = re.compile(r"^ses[A-Za-z0-9_-]{1,128}$")
_PERMISSION_ID = re.compile(r"^per[A-Za-z0-9_-]{1,128}$")
_EVENT_ID = re.compile(r"^evt_[A-Za-z0-9_-]{1,128}$")
_SAFE_ACTION = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_DECISIONS = frozenset({"once", "reject"})
_SESSION_EVENTS = frozenset({
    "session.execution.started",
    "session.execution.succeeded",
    "session.execution.failed",
    "session.execution.interrupted",
    "session.step.started",
    "session.step.ended",
    "session.step.failed",
    "permission.asked",
    "permission.replied",
})


def _valid_identifier(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def default_session_permissions() -> list[dict[str, str]]:
    """Require an explicit user decision for every OpenCode permission action."""
    return [{"action": "*", "resource": "*", "effect": "ask"}]


def normalize_permission_request(payload: object, expected_session_id: str) -> dict[str, Any]:
    """Reduce a permission request to bounded, session-bound display metadata."""
    if not _valid_identifier(expected_session_id, _SESSION_ID):
        raise ValueError("opencode_session_id_invalid")
    if not isinstance(payload, dict):
        raise ValueError("opencode_permission_payload_invalid")
    request_id = payload.get("id")
    if not _valid_identifier(request_id, _PERMISSION_ID):
        raise ValueError("opencode_permission_id_invalid")
    if payload.get("sessionID") != expected_session_id:
        raise ValueError("opencode_permission_session_mismatch")
    action = payload.get("action")
    resources = payload.get("resources")
    if not isinstance(action, str) or not _SAFE_ACTION.fullmatch(action):
        raise ValueError("opencode_permission_action_invalid")
    if not isinstance(resources, list) or not 1 <= len(resources) <= 64:
        raise ValueError("opencode_permission_resources_invalid")
    safe_resources: list[str] = []
    for resource in resources:
        if not isinstance(resource, str) or not resource or len(resource) > 1024:
            raise ValueError("opencode_permission_resource_invalid")
        if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in resource):
            raise ValueError("opencode_permission_resource_invalid")
        safe_resources.append(resource)
    return {
        "request_id": request_id,
        "session_id": expected_session_id,
        "action": action,
        "resources": safe_resources,
    }


def permission_reply_body(request_id: str, decision: str) -> dict[str, str]:
    """Build a one-request reply; permanent/saved grants are never expressible."""
    if not _valid_identifier(request_id, _PERMISSION_ID):
        raise ValueError("opencode_permission_id_invalid")
    if not isinstance(decision, str) or decision not in _SAFE_DECISIONS:
        raise ValueError("opencode_permission_decision_invalid")
    return {"decision": decision}


def safe_event_metadata(payload: object, expected_session_id: str) -> dict[str, str | float] | None:
    """Keep only coarse session lifecycle and exact once/reject permission metadata."""
    if not _valid_identifier(expected_session_id, _SESSION_ID) or not isinstance(payload, dict):
        return None
    event_id = payload.get("id")
    event_type = payload.get("type")
    data = payload.get("data")
    if (
        not _valid_identifier(event_id, _EVENT_ID)
        or not isinstance(event_type, str)
        or event_type not in _SESSION_EVENTS
        or not isinstance(data, dict)
        or data.get("sessionID") != expected_session_id
    ):
        return None
    result: dict[str, str | float] = {"event": event_type}
    if event_type == "permission.asked":
        request_id = data.get("id")
        if not _valid_identifier(request_id, _PERMISSION_ID):
            return None
        result["permission_request_id"] = request_id
    elif event_type == "permission.replied":
        request_id = data.get("requestID")
        decision = data.get("reply")
        if (
            not _valid_identifier(request_id, _PERMISSION_ID)
            or not isinstance(decision, str)
            or decision not in _SAFE_DECISIONS
        ):
            return None
        result["permission_request_id"] = request_id
        result["decision"] = decision
    created = payload.get("created")
    if (
        isinstance(created, (int, float))
        and not isinstance(created, bool)
        and 0 <= created <= 4_102_444_800
    ):
        try:
            if math.isfinite(created):
                result["created"] = float(created)
        except (OverflowError, TypeError, ValueError):
            pass
    return result
