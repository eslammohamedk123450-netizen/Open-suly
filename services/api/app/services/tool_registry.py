"""Small, explicit registry for safe worker operations."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from app.services.task_worker import ClaimedStep

ToolHandler = Callable[[ClaimedStep], dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    permission_scope: str
    allowed_input_fields: frozenset[str]
    required_input_fields: frozenset[str]
    max_input_bytes: int
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"duplicate_tool:{definition.name}")
        if not definition.name or definition.max_input_bytes < 1:
            raise ValueError("invalid_tool_definition")
        if not definition.required_input_fields <= definition.allowed_input_fields:
            raise ValueError("required_fields_must_be_allowed")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def describe(self) -> list[dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description, "permission_scope": tool.permission_scope}
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    def execute(self, step: ClaimedStep) -> dict[str, Any]:
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
            encoded = json.dumps(step.input, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_tool_input: input must be JSON serializable") from exc
        if len(encoded) > tool.max_input_bytes:
            raise ValueError("tool_input_too_large")
        return tool.handler(step)
