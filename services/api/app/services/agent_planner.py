"""Deterministic, allow-listed task planning.

This is a safe baseline planner, not an LLM planner. It only emits a plan for
an explicitly requested operation that the worker runtime can execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannedTask:
    steps: list[dict[str, Any]]
    planner: str = "deterministic-v1"


class UnsupportedTaskRequest(ValueError):
    pass


_PREFIXES = ("analyze:", "analyse:", "حلل:", "حلّل:")
_AGENT_PREFIXES = ("agent:", "وكيل:")


def plan_request(request: str) -> PlannedTask:
    if not isinstance(request, str) or not request.strip():
        raise UnsupportedTaskRequest("Task request is empty.")
    normalized = request.strip()
    lowered = normalized.lower()
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
            not settings.hermes_agent_enabled
            or not settings.hermes_agent_isolation_confirmed
            or not settings.hermes_agent_base_url
            or settings.hermes_agent_api_key is None
        ):
            raise UnsupportedTaskRequest(
                "The general agent is unavailable until the isolated Hermes runtime is explicitly enabled."
            )
        if TOOL_REGISTRY.get("hermes.agent.turn") is None:
            raise UnsupportedTaskRequest("The general agent is not registered in the worker runtime.")
        return PlannedTask(steps=[{
            "step_key": "general_agent",
            "title": "Execute general agent task",
            "description": "Run the task through the approved, isolated general-agent engine.",
            "depends_on": [],
            "input": {"operation": "hermes.agent.turn", "prompt": prompt},
        }], planner="agent-routing-v1")

    prefix = next((item for item in _PREFIXES if lowered.startswith(item)), None)
    if prefix is None:
        raise UnsupportedTaskRequest(
            "This request needs a supported operation. Use analyze: for deterministic text analysis "
            "or agent: for the explicitly enabled general agent."
        )
    text = normalized[len(prefix):].strip()
    if not text:
        raise UnsupportedTaskRequest("Provide the text to analyze after the operation prefix.")
    if len(text) > 20000:
        raise UnsupportedTaskRequest("Text analysis input exceeds 20,000 characters.")
    # Keep planning and execution capabilities in sync: a planner may only emit
    # an operation currently registered by the worker runtime.
    from app.worker_runtime import TOOL_REGISTRY

    if TOOL_REGISTRY.get("text.analyze") is None:
        raise UnsupportedTaskRequest("Text analysis is not available in the current worker registry.")
    return PlannedTask(steps=[{
        "step_key": "analyze_text",
        "title": "Analyze supplied text",
        "description": "Compute deterministic text statistics and a short preview.",
        "depends_on": [],
        "input": {"operation": "text.analyze", "text": text},
    }])
