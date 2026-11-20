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
