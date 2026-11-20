from __future__ import annotations

import pytest

from app.services.opencode_event_consumer import iter_sse_data
from app.services.opencode_approval_manager import OpenCodeApprovalManager
from app.services.opencode_lifecycle_store import _safe_json


def test_sse_parser_handles_multiline_data_and_crlf():
    frames = list(iter_sse_data(iter([
        b": heartbeat\r\ndata: {\"type\":\r\n",
        b"data: \"session.idle\"}\r\n\r\n",
    ])))
    assert frames == [b'{\"type\":\n\"session.idle\"}']


def test_sse_parser_rejects_unterminated_oversized_line():
    with pytest.raises(ValueError, match="sse_line_too_large"):
        list(iter_sse_data(iter([b"x" * 40]), max_line=32))


def test_sse_parser_rejects_oversized_event():
    with pytest.raises(ValueError, match="sse_event_too_large"):
        list(iter_sse_data(iter([b"data: " + b"x" * 40 + b"\n\n"]), max_event=32))


def test_sse_parser_rejects_truncated_frame():
    with pytest.raises(ValueError, match="sse_stream_ended_mid_event"):
        list(iter_sse_data(iter([b"data: {\"x\":1}"])))


def test_event_payload_rejects_secret_fields_recursively():
    with pytest.raises(ValueError, match="opencode_sensitive_event_field"):
        _safe_json({"nested": [{"api_key": "do-not-store"}]}, limit=1024)


def test_event_payload_enforces_size_limit():
    with pytest.raises(ValueError, match="opencode_payload_too_large"):
        _safe_json({"data": "x" * 100}, limit=32)


def test_approval_gateway_url_is_https_and_runtime_scoped():
    runtime_id = "00000000-0000-4000-8000-000000000001"
    url = OpenCodeApprovalManager._gateway_url(
        "https://runtime.example.test",
        f"/v1/runtime-gateway/{runtime_id}",
        "/api/session/sesABC123/permission",
    )
    assert url == (
        f"https://runtime.example.test/v1/runtime-gateway/{runtime_id}"
        "/api/session/sesABC123/permission"
    )


def test_approval_gateway_rejects_non_https_origin_and_path_traversal():
    runtime_id = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(ValueError, match="opencode_gateway_origin_invalid"):
        OpenCodeApprovalManager._gateway_url(
            "http://runtime.example.test", f"/v1/runtime-gateway/{runtime_id}", "/event"
        )
    with pytest.raises(ValueError, match="opencode_gateway_route_invalid"):
        OpenCodeApprovalManager._gateway_url(
            "https://runtime.example.test", f"/v1/runtime-gateway/{runtime_id}", "/../admin"
        )

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
