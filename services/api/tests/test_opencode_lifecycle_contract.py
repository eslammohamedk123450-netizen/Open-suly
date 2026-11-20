from app.services.opencode_contract import safe_event_metadata, permission_reply_body
from app.services.opencode_event_consumer import OpenCodeEventConsumer


def test_event_consumer_targets_the_original_opencode_event_route():
    runtime_id = "00000000-0000-4000-8000-000000000001"
    assert OpenCodeEventConsumer._url(
        "https://runtime.example.test", f"/v1/runtime-gateway/{runtime_id}"
    ).endswith("/api/event")


def test_original_event_contract_reduces_only_expected_session_metadata():
    event = {
        "id": "evt_123",
        "type": "permission.asked",
        "data": {
            "sessionID": "sesABC123",
            "id": "perABC123",
            "action": "file.write",
            "resources": ["/workspace/src/main.py"],
            "metadata": {"prompt": "private"},
        },
        "created": 1795220000,
    }
    safe = safe_event_metadata(event, "sesABC123")
    assert safe == {
        "event": "permission.asked",
        "permission_request_id": "perABC123",
        "created": 1795220000.0,
    }
    assert safe_event_metadata(event, "sesOTHER123") is None


def test_upstream_permission_replies_cannot_create_permanent_grants():
    assert permission_reply_body("perABC123", "once") == {"decision": "once"}
    assert permission_reply_body("perABC123", "reject") == {"decision": "reject"}
    with pytest.raises(ValueError, match="decision_invalid"):
        permission_reply_body("perABC123", "always")
