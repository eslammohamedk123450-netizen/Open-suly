from __future__ import annotations

import pytest

from app.services import opencode_contract


SESSION_ID = "ses_taskrun_123456789"
PERMISSION_ID = "per_request_123456"


def test_opencode_session_defaults_to_ask_for_every_action():
    assert opencode_contract.default_session_permissions() == [
        {"action": "*", "resource": "*", "effect": "ask"},
    ]


def test_opencode_permission_request_is_reduced_and_bound_to_exact_session():
    result = opencode_contract.normalize_permission_request({
        "id": PERMISSION_ID,
        "sessionID": SESSION_ID,
        "action": "bash",
        "resources": ["git status"],
        "message": "untrusted model-generated text",
        "metadata": {"secret": "must not escape"},
        "save": ["always"],
        "source": {"type": "tool", "messageID": "msg_1", "id": "tool_1"},
    }, SESSION_ID)
    assert result == {
        "request_id": PERMISSION_ID,
        "session_id": SESSION_ID,
        "action": "bash",
        "resources": ["git status"],
    }


def test_opencode_permission_request_rejects_cross_session_and_invalid_fields():
    payload = {"id": PERMISSION_ID, "sessionID": SESSION_ID, "action": "read", "resources": ["src/main.py"]}
    with pytest.raises(ValueError, match="session_mismatch"):
        opencode_contract.normalize_permission_request({**payload, "sessionID": "ses_other_123456"}, SESSION_ID)
    with pytest.raises(ValueError, match="resources_invalid"):
        opencode_contract.normalize_permission_request({**payload, "resources": []}, SESSION_ID)
    with pytest.raises(ValueError, match="resource_invalid"):
        opencode_contract.normalize_permission_request({**payload, "resources": ["bad\nresource"]}, SESSION_ID)
    with pytest.raises(ValueError, match="action_invalid"):
        opencode_contract.normalize_permission_request({**payload, "action": "bash" + chr(0x202E)}, SESSION_ID)
    with pytest.raises(ValueError, match="action_invalid"):
        opencode_contract.normalize_permission_request({**payload, "action": "bash action"}, SESSION_ID)
    with pytest.raises(ValueError, match="resource_invalid"):
        opencode_contract.normalize_permission_request({**payload, "resources": ["src" + chr(0x202E) + "/main.py"]}, SESSION_ID)



@pytest.mark.parametrize("decision", ["once", "reject"])
def test_opencode_permission_reply_only_allows_single_request_decisions(decision):
    assert opencode_contract.permission_reply_body(PERMISSION_ID, decision) == {"decision": decision}


@pytest.mark.parametrize("decision", ["always", "allow", "", [], {}])
def test_opencode_permission_reply_rejects_permanent_or_malformed_decisions(decision):
    with pytest.raises(ValueError, match="decision_invalid"):
        opencode_contract.permission_reply_body(PERMISSION_ID, decision)


def test_opencode_event_reducer_keeps_only_session_lifecycle_metadata():
    event = opencode_contract.safe_event_metadata({
        "id": "evt_123456789",
        "type": "session.execution.started",
        "created": 1_800_000_000,
        "data": {"sessionID": SESSION_ID, "prompt": "private prompt", "reasoning": "private reasoning"},
        "metadata": {"anything": "private"},
    }, SESSION_ID)
    assert event == {"event": "session.execution.started", "created": 1_800_000_000.0}


def test_opencode_event_reducer_binds_permission_events_and_rejects_always():
    asked = opencode_contract.safe_event_metadata({
        "id": "evt_123456789",
        "type": "permission.asked",
        "data": {"sessionID": SESSION_ID, "id": PERMISSION_ID, "action": "bash", "resources": ["git status"], "message": "ignore safety"},
    }, SESSION_ID)
    assert asked == {"event": "permission.asked", "permission_request_id": PERMISSION_ID}
    replied = opencode_contract.safe_event_metadata({
        "id": "evt_123456789",
        "type": "permission.replied",
        "data": {"sessionID": SESSION_ID, "requestID": PERMISSION_ID, "reply": "once"},
    }, SESSION_ID)
    assert replied == {"event": "permission.replied", "permission_request_id": PERMISSION_ID, "decision": "once"}
    assert opencode_contract.safe_event_metadata({
        "id": "evt_123456789",
        "type": "permission.replied",
        "data": {"sessionID": SESSION_ID, "requestID": PERMISSION_ID, "reply": "always"},
    }, SESSION_ID) is None


def test_opencode_event_reducer_drops_cross_session_unknown_and_malformed_events():
    base = {"id": "evt_123456789", "type": "session.execution.started", "data": {"sessionID": SESSION_ID}}
    assert opencode_contract.safe_event_metadata(base, "ses_another_123456") is None
    assert opencode_contract.safe_event_metadata({**base, "type": "session.text.delta"}, SESSION_ID) is None
    assert opencode_contract.safe_event_metadata({**base, "id": "not-an-event"}, SESSION_ID) is None
    malformed = {"id": "evt_123456789", "type": "permission.replied", "data": {"sessionID": SESSION_ID, "requestID": PERMISSION_ID, "reply": []}}
    assert opencode_contract.safe_event_metadata(malformed, SESSION_ID) is None


def test_opencode_event_reducer_ignores_extreme_or_nonfinite_timestamps():
    base = {"id": "evt_123456789", "type": "session.execution.started", "data": {"sessionID": SESSION_ID}}
    assert opencode_contract.safe_event_metadata({**base, "created": 10**1000}, SESSION_ID) == {
        "event": "session.execution.started",
    }
    assert opencode_contract.safe_event_metadata({**base, "created": float("nan")}, SESSION_ID) == {
        "event": "session.execution.started",
    }