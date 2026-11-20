"""Explicit allow-list and approval gate for worker tools."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable

from app.services.task_worker import ClaimedStep

ToolHandler = Callable[[ClaimedStep], dict[str, Any]]


@dataclass(frozen=True)
class ToolExecutionContext:
    """Trusted server-created grants; never construct this from task input."""
    approved_scopes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    permission_scope: str
    allowed_input_fields: frozenset[str]
    required_input_fields: frozenset[str]
    max_input_bytes: int
    handler: ToolHandler
    requires_approval: bool = True
    max_output_bytes: int = 64_000


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"duplicate_tool:{definition.name}")
        if (
            not definition.name
            or not definition.permission_scope
            or definition.max_input_bytes < 1
            or definition.max_output_bytes < 1
        ):
            raise ValueError("invalid_tool_definition")
        if not definition.required_input_fields <= definition.allowed_input_fields:
            raise ValueError("required_fields_must_be_allowed")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def requires_approval_scope(self, scope: str) -> bool:
        return any(tool.requires_approval and tool.permission_scope == scope for tool in self._tools.values())

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permission_scope": tool.permission_scope,
                "requires_approval": tool.requires_approval,
                "allowed_input_fields": sorted(tool.allowed_input_fields),
                "required_input_fields": sorted(tool.required_input_fields),
                "max_input_bytes": tool.max_input_bytes,
                "max_output_bytes": tool.max_output_bytes,
            }
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def execute(
        self,
        step: ClaimedStep,
        context: ToolExecutionContext | None = None,
    ) -> dict[str, Any]:
        if not isinstance(step.input, dict):
            raise ValueError("invalid_tool_input: input must be an object")
        if any(not isinstance(key, str) for key in step.input):
            raise ValueError("invalid_tool_input: object keys must be strings")
        operation = step.input.get("operation")
        if not isinstance(operation, str):
            raise ValueError("unsupported_operation: operation must be a string")
        tool = self.get(operation)
        if tool is None:
            raise ValueError("unsupported_operation: operation is not registered")
        unexpected = set(step.input) - (set(tool.allowed_input_fields) | {"operation"})
        if unexpected:
            raise ValueError("invalid_tool_input: unexpected input field")
        if tool.required_input_fields - set(step.input):
            raise ValueError("invalid_tool_input: required input field is missing")
        try:
            encoded = json.dumps(
                step.input, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_tool_input: input must be JSON serializable") from exc
        if len(encoded) > tool.max_input_bytes:
            raise ValueError("tool_input_too_large")
        grants = context.approved_scopes if context is not None else frozenset()
        if tool.requires_approval and tool.permission_scope not in grants:
            raise PermissionError(f"tool_approval_required:{tool.permission_scope}")
        result = tool.handler(step)
        if not isinstance(result, dict):
            raise ValueError("invalid_tool_output: handler must return an object")
        try:
            if any(not isinstance(key, str) for key in result):
                raise ValueError("output object keys must be strings")
            output = json.dumps(
                result, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_tool_output: result must be JSON serializable") from exc
        if len(output) > tool.max_output_bytes:
            raise ValueError("tool_output_too_large")
        return result
