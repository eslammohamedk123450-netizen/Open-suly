"""Deterministic, allow-listed task planning.

This is a safe baseline planner, not an LLM planner. It only emits a plan for
an explicitly requested operation that the worker runtime can execute.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


@dataclass(frozen=True)
class PlannedTask:
    steps: list[dict[str, Any]]
    planner: str = "deterministic-v1"


class UnsupportedTaskRequest(ValueError):
    pass


_STEP_KEY = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def validate_agent_plan(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate an agent-produced DAG against the worker's explicit tool allow-list."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
        raise UnsupportedTaskRequest("Agent plan must contain between 1 and 32 steps.")
    from app.worker_runtime import TOOL_REGISTRY

    normalized: list[dict[str, Any]] = []
    by_key: dict[str, set[str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            raise UnsupportedTaskRequest("Agent plan step must be an object.")
        if set(step) - {"step_key", "title", "description", "depends_on", "input"}:
            raise UnsupportedTaskRequest("Agent plan step contains unsupported fields.")
        key = step.get("step_key")
        title = step.get("title")
        description = step.get("description", "")
        dependencies = step.get("depends_on", [])
        payload = step.get("input")
        if not isinstance(key, str) or not _STEP_KEY.fullmatch(key) or key in by_key:
            raise UnsupportedTaskRequest("Agent plan contains an invalid or duplicate step key.")
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise UnsupportedTaskRequest("Agent plan step title is invalid.")
        if not isinstance(description, str) or len(description) > 1000:
            raise UnsupportedTaskRequest("Agent plan step description is invalid.")
        if (
            not isinstance(dependencies, list)
            or any(not isinstance(dep, str) for dep in dependencies)
            or len(dependencies) != len(set(dependencies))
            or key in dependencies
        ):
            raise UnsupportedTaskRequest("Agent plan dependencies are invalid.")
        if not isinstance(payload, dict) or not isinstance(payload.get("operation"), str):
            raise UnsupportedTaskRequest("Agent plan step operation is invalid.")
        tool = TOOL_REGISTRY.get(payload["operation"])
        if tool is None:
            raise UnsupportedTaskRequest("Agent plan references an unregistered operation.")
        unexpected = set(payload) - (set(tool.allowed_input_fields) | {"operation"})
        if unexpected or tool.required_input_fields - set(payload):
            raise UnsupportedTaskRequest("Agent plan input fields violate the tool contract.")
        try:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise UnsupportedTaskRequest("Agent plan input is not valid JSON.") from exc
        if len(encoded) > tool.max_input_bytes:
            raise UnsupportedTaskRequest("Agent plan step input exceeds the tool limit.")
        by_key[key] = set(dependencies)
        normalized.append({
            "step_key": key,
            "title": title.strip(),
            "description": description,
            "depends_on": list(dependencies),
            "input": payload,
        })

    known = set(by_key)
    if any(dependencies - known for dependencies in by_key.values()):
        raise UnsupportedTaskRequest("Agent plan references a missing dependency.")
    positions = {step["step_key"]: index for index, step in enumerate(normalized)}
    if any(
        positions[dependency] >= positions[key]
        for key, dependencies in by_key.items()
        for dependency in dependencies
    ):
        raise UnsupportedTaskRequest("Agent plan dependencies must refer to earlier steps.")
    remaining = {key: set(dependencies) for key, dependencies in by_key.items()}
    completed: set[str] = set()
    while remaining:
        ready = {key for key, dependencies in remaining.items() if dependencies <= completed}
        if not ready:
            raise UnsupportedTaskRequest("Agent plan contains a dependency cycle.")
        completed.update(ready)
        for key in ready:
            remaining.pop(key)
    return normalized


_PREFIXES = ("analyze:", "analyse:", "حلل:", "حلّل:")
_AGENT_PREFIXES = ("agent:", "وكيل:")
_TEAM_PREFIXES = ("team:", "فريق:")


def plan_request(request: str) -> PlannedTask:
    if not isinstance(request, str) or not request.strip():
        raise UnsupportedTaskRequest("Task request is empty.")
    normalized = request.strip()
    lowered = normalized.lower()
    team_prefix = next((item for item in _TEAM_PREFIXES if lowered.startswith(item)), None)
    if team_prefix is not None:
        prompt = normalized[len(team_prefix):].strip()
        if not prompt:
            raise UnsupportedTaskRequest("Provide the team task after the team: prefix.")
        if len(prompt) > 8_000:
            raise UnsupportedTaskRequest("Team task input exceeds 8,000 characters.")
        from app.core.config import get_settings
        from app.worker_runtime import TOOL_REGISTRY

        settings = get_settings()
        if (
            not settings.worker_enabled
            or not settings.hermes_agent_enabled
            or not settings.opencode_enabled
            or not settings.runtime_provisioner_url
            or not settings.runtime_provisioner_token
            or not settings.runtime_provisioner_allowed_origins
        ):
            raise UnsupportedTaskRequest(
                "The two-engine team is unavailable until Hermes, OpenCode and their isolated runtime provisioner are explicitly enabled."
            )
        if TOOL_REGISTRY.get("hermes.agent.turn") is None or TOOL_REGISTRY.get("engine.collaborate") is None:
            raise UnsupportedTaskRequest("The cross-engine collaboration operation is not registered.")
        return PlannedTask(steps=validate_agent_plan([
            {
                "step_key": "hermes_prepare",
                "title": "Hermes analysis and preparation",
                "description": "Hermes prepares a bounded plan and task context for the coding engine.",
                "depends_on": [],
                "input": {"operation": "hermes.agent.turn", "prompt": prompt},
            },
            {
                "step_key": "opencode_handoff",
                "title": "OpenCode implementation handoff",
                "description": "OpenCode receives the completed Hermes output through the SULY collaboration boundary.",
                "depends_on": ["hermes_prepare"],
                "input": {
                    "operation": "engine.collaborate",
                    "target_engine": "opencode",
                    "source_step_key": "hermes_prepare",
                    "capability": "code.edit",
                    "prompt": prompt,
                    "title": "SULY team implementation",
                },
            },
        ]), planner="engine-team-v1")

    agent_prefix = next((item for item in _AGENT_PREFIXES if lowered.startswith(item)), None)
    if agent_prefix is not None:
        prompt = normalized[len(agent_prefix):].strip()
        if not prompt:
            raise UnsupportedTaskRequest("Provide the agent task after the agent: prefix.")
        if len(prompt) > 20000:
            raise UnsupportedTaskRequest("Agent task input exceeds 20,000 characters.")
        from app.core.config import get_settings
        from app.worker_runtime import TOOL_REGISTRY

        settings = get_settings()
        if (
            not settings.worker_enabled
            or not settings.hermes_agent_enabled
            or not settings.runtime_provisioner_url
            or not settings.runtime_provisioner_token
            or not settings.runtime_provisioner_allowed_origins
        ):
            raise UnsupportedTaskRequest(
                "The general agent is unavailable until the isolated Hermes runtime is explicitly enabled."
            )
        if TOOL_REGISTRY.get("hermes.agent.turn") is None:
            raise UnsupportedTaskRequest("The general agent is not registered in the worker runtime.")
        return PlannedTask(steps=validate_agent_plan([{
            "step_key": "general_agent",
            "title": "Execute general agent task",
            "description": "Run the task through the approved, isolated general-agent engine.",
            "depends_on": [],
            "input": {"operation": "hermes.agent.turn", "prompt": prompt},
        }]), planner="agent-routing-v1")

    prefix = next((item for item in _PREFIXES if lowered.startswith(item)), None)
    if prefix is None:
        raise UnsupportedTaskRequest(
            "This request needs a supported operation. Current planner supports text analysis only; "
            "use agent: for the explicitly enabled general agent."
        )
    text = normalized[len(prefix):].strip()
    if not text:
        raise UnsupportedTaskRequest("Provide the text to analyze after the operation prefix.")
    if len(text) > 20000:
        raise UnsupportedTaskRequest("Text analysis input exceeds 20,000 characters.")
    # لا نضع مهامًا في الطابور إذا كان لا يوجد worker قادر على تنفيذها.
    from app.core.config import get_settings
    from app.worker_runtime import TOOL_REGISTRY

    if not get_settings().worker_enabled:
        raise UnsupportedTaskRequest("The task worker is disabled on the server.")
    if TOOL_REGISTRY.get("text.analyze") is None:
        raise UnsupportedTaskRequest("Text analysis is not available in the current worker registry.")
    return PlannedTask(steps=validate_agent_plan([{
        "step_key": "analyze_text",
        "title": "Analyze supplied text",
        "description": "Compute deterministic text statistics and a short preview.",
        "depends_on": [],
        "input": {"operation": "text.analyze", "text": text},
    }]))
