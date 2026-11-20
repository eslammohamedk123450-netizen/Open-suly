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


def plan_request(request: str) -> PlannedTask:
    if not isinstance(request, str) or not request.strip():
        raise UnsupportedTaskRequest("Task request is empty.")
    normalized = request.strip()
    lowered = normalized.lower()
    prefix = next((item for item in _PREFIXES if lowered.startswith(item)), None)
    if prefix is None:
        raise UnsupportedTaskRequest(
            "This request needs a supported operation. Current planner supports "
            "explicit text analysis only; no generic agent plan was generated."
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
