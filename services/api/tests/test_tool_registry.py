from dataclasses import replace
from uuid import UUID

import pytest

from app.services.tool_registry import ToolDefinition, ToolExecutionContext, ToolRegistry
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
    assert [tool["name"] for tool in tools] == ["ai.respond", "hermes.agent.turn", "opencode.task.run", "text.analyze"]
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["ai.respond"]["requires_approval"] is True
    assert by_name["text.analyze"]["requires_approval"] is False
    assert by_name["ai.respond"]["permission_scope"] == "ai.provider.run"
    assert by_name["ai.respond"]["allowed_input_fields"] == ["prompt"]
    assert by_name["ai.respond"]["required_input_fields"] == ["prompt"]
    assert by_name["text.analyze"]["permission_scope"] == "task.text.analyze"
    assert by_name["hermes.agent.turn"]["permission_scope"] == "agent.hermes.run"
    assert by_name["hermes.agent.turn"]["allowed_input_fields"] == ["prompt", "runtime_budget_seconds"]
    assert by_name["hermes.agent.turn"]["required_input_fields"] == ["prompt"]
    assert by_name["hermes.agent.turn"]["max_input_bytes"] == 20_200
    assert by_name["hermes.agent.turn"]["max_output_bytes"] == 52_000
    assert by_name["text.analyze"]["allowed_input_fields"] == ["text"]


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
        requires_approval=True,
    )
    registry.register(definition)
    with pytest.raises(ValueError, match="duplicate_tool"):
        registry.register(definition)
    with pytest.raises(ValueError, match="required_fields_must_be_allowed"):
        registry.register(replace(definition, name="bad", required_input_fields=frozenset({"missing"})))


def test_sensitive_tool_requires_explicit_trusted_scope_grant():
    registry = ToolRegistry()
    called = []
    registry.register(ToolDefinition(
        name="external.lookup",
        description="Example external lookup",
        permission_scope="external.lookup",
        allowed_input_fields=frozenset({"query"}),
        required_input_fields=frozenset({"query"}),
        max_input_bytes=100,
        handler=lambda _step: called.append(True) or {"ok": True},
        requires_approval=True,
    ))
    step = make_step({"operation": "external.lookup", "query": "test"})
    with pytest.raises(PermissionError, match="tool_approval_required"):
        registry.execute(step)
    assert called == []
    result = registry.execute(step, ToolExecutionContext(approved_scopes=frozenset({"external.lookup"})))
    assert result == {"ok": True}
    assert called == [True]


def test_task_payload_cannot_self_grant_tool_permission():
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="external.lookup",
        description="Example external lookup",
        permission_scope="external.lookup",
        allowed_input_fields=frozenset({"query"}),
        required_input_fields=frozenset({"query"}),
        max_input_bytes=100,
        handler=lambda _step: {"ok": True},
        requires_approval=True,
    ))
    step = make_step({
        "operation": "external.lookup",
        "query": "test",
        "approved_scopes": ["external.lookup"],
    })
    with pytest.raises(ValueError, match="unexpected input field"):
        registry.execute(step)


def test_registry_validates_handler_output_type_and_size():
    registry = ToolRegistry()
    step = make_step({"operation": "output.test", "value": "x"})
    registry.register(ToolDefinition(
        name="output.test",
        description="Output validation test",
        permission_scope="output.test",
        allowed_input_fields=frozenset({"value"}),
        required_input_fields=frozenset({"value"}),
        max_input_bytes=100,
        max_output_bytes=10,
        handler=lambda _step: {"long": "this output is too large"},
        requires_approval=False,
    ))
    with pytest.raises(ValueError, match="tool_output_too_large"):
        registry.execute(step)

    invalid = ToolRegistry()
    invalid.register(ToolDefinition(
        name="output.test",
        description="Invalid output test",
        permission_scope="output.test",
        allowed_input_fields=frozenset({"value"}),
        required_input_fields=frozenset({"value"}),
        max_input_bytes=100,
        handler=lambda _step: object(),
        requires_approval=False,
    ))
    with pytest.raises(ValueError, match="invalid_tool_output"):
        invalid.execute(step)


def test_registry_rejects_non_object_input_before_lookup():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="input must be an object"):
        registry.execute(replace(make_step({}), input=["not", "an", "object"]))


@pytest.mark.parametrize("bad_output", [
    {"value": float("nan")},
    {"value": float("inf")},
    {1: "non-string key"},
])
def test_registry_rejects_non_strict_json_outputs(bad_output):
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="strict.output",
        description="Strict JSON output validation",
        permission_scope="strict.output",
        allowed_input_fields=frozenset({"value"}),
        required_input_fields=frozenset({"value"}),
        max_input_bytes=100,
        handler=lambda _step: bad_output,
        requires_approval=False,
    ))
    with pytest.raises(ValueError, match="invalid_tool_output"):
        registry.execute(make_step({"operation": "strict.output", "value": "ok"}))



@pytest.mark.parametrize("bad_input", [
    {"operation": "text.analyze", "text": float("nan")},
    {"operation": "text.analyze", "text": float("inf")},
    {"operation": "text.analyze", 7: "non-string key"},
])
def test_registry_rejects_non_strict_json_inputs(bad_input):
    with pytest.raises(ValueError, match="invalid_tool_input"):
        dispatch(make_step(bad_input))
