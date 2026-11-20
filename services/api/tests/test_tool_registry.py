from dataclasses import replace
from uuid import UUID

import pytest

from app.services.tool_registry import ToolDefinition, ToolRegistry
from app.services.task_worker import ClaimedStep
from app.worker_runtime import TOOL_REGISTRY, dispatch


def make_step(input_data):
    return ClaimedStep(
        step_id=UUID("00000000-0000-0000-0000-000000000001"),
        task_id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        step_key="test",
        title="Test tool",
        description="",
        input=input_data,
        attempt_count=1,
        max_attempts=3,
        lease_token=UUID("00000000-0000-0000-0000-000000000004"),
        lease_expires_at="2026-11-20T12:00:00+00:00",
    )


def test_registry_exposes_only_registered_tool_metadata():
    tools = TOOL_REGISTRY.describe()
    assert [tool["name"] for tool in tools] == ["text.analyze"]
    assert tools[0]["permission_scope"] == "task.text.analyze"


def test_registry_rejects_unknown_operation_and_unexpected_fields():
    with pytest.raises(ValueError, match="unsupported_operation"):
        dispatch(make_step({"operation": "shell.exec", "command": "id"}))
    with pytest.raises(ValueError, match="unexpected input field"):
        dispatch(make_step({"operation": "text.analyze", "text": "safe", "path": "/etc/passwd"}))


def test_registry_enforces_required_fields_and_input_size():
    with pytest.raises(ValueError, match="required input field"):
        dispatch(make_step({"operation": "text.analyze"}))
    with pytest.raises(ValueError, match="tool_input_too_large"):
        dispatch(make_step({"operation": "text.analyze", "text": "x" * 24_001}))


def test_registry_rejects_duplicate_names_and_invalid_field_schema():
    registry = ToolRegistry()
    definition = ToolDefinition(
        name="demo",
        description="demo",
        permission_scope="demo.run",
        allowed_input_fields=frozenset({"value"}),
        required_input_fields=frozenset({"value"}),
        max_input_bytes=100,
        handler=lambda _step: {"ok": True},
    )
    registry.register(definition)
    with pytest.raises(ValueError, match="duplicate_tool"):
        registry.register(definition)
    with pytest.raises(ValueError, match="required_fields_must_be_allowed"):
        registry.register(replace(definition, name="bad", required_input_fields=frozenset({"missing"})))
