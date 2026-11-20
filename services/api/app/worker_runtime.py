"""Allow-listed, provider-independent task worker runtime.

Only registered operations can execute. No arbitrary Python, shell, browser,
filesystem, or external provider calls are available in this runtime.
"""
from __future__ import annotations

import logging
import os
import signal
from threading import Event
from typing import Any, Callable

from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.hermes_agent import run_agent_turn
from app.services.task_worker import ClaimedStep, TaskWorker
from app.services.tool_registry import ToolDefinition, ToolExecutionContext, ToolRegistry
from app.services.tool_approvals import ToolApprovalStore

logger = logging.getLogger("suly.worker")


def text_analyze(step: ClaimedStep) -> dict[str, Any]:
    text = step.input.get("text")
    if not isinstance(text, str):
        raise ValueError("text.analyze requires a string input.text")
    words = text.split()
    return {
        "operation": "text.analyze",
        "character_count": len(text),
        "word_count": len(words),
        "line_count": len(text.splitlines()) or (1 if text else 0),
        "preview": text[:500],
    }


def hermes_agent_turn(step: ClaimedStep) -> dict[str, Any]:
    prompt = step.input.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("hermes.agent.turn requires a string input.prompt")
    result = run_agent_turn(prompt)
    return {
        "operation": "hermes.agent.turn",
        "engine": result["engine"],
        "content": result["content"],
    }


def dispatch_cancel_aware(
    step: ClaimedStep,
    cancel_event: Event,
    approval_store: ToolApprovalStore | None = None,
) -> dict[str, Any]:
    """Refuse to start an operation after the worker loses its lease or is cancelled.

    The worker still owns the authoritative lease check before checkpointing;
    this event is a cooperative stop signal, never an authorization grant.
    """
    if cancel_event.is_set():
        raise RuntimeError("task_execution_cancelled")
    return dispatch(step, approval_store)


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        name="text.analyze",
        description="Count words, characters, and lines in supplied text",
        permission_scope="task.text.analyze",
        allowed_input_fields=frozenset({"text"}),
        required_input_fields=frozenset({"text"}),
        max_input_bytes=24_000,
        handler=text_analyze,
        requires_approval=False,
    ))
    registry.register(ToolDefinition(
        name="hermes.agent.turn",
        description="Run one bounded user prompt through the optional Hermes Agent engine",
        permission_scope="agent.hermes.run",
        allowed_input_fields=frozenset({"prompt"}),
        required_input_fields=frozenset({"prompt"}),
        max_input_bytes=20_100,
        handler=hermes_agent_turn,
        requires_approval=True,
        max_output_bytes=52_000,
    ))
    return registry


TOOL_REGISTRY = build_tool_registry()


def dispatch(
    step: ClaimedStep,
    approval_store: ToolApprovalStore | None = None,
) -> dict[str, Any]:
    # Fetch persisted consent immediately before execution so revocation takes
    # effect on the next attempt; never derive grants from task payloads.
    scopes = approval_store.active_scopes(str(step.user_id)) if approval_store else frozenset()
    return TOOL_REGISTRY.execute(step, ToolExecutionContext(approved_scopes=scopes))


class WorkerRuntime:
    def __init__(
        self,
        worker: TaskWorker,
        *,
        poll_interval_seconds: float = 2.0,
        idle_backoff_max_seconds: float = 15.0,
        handler: Callable[[ClaimedStep], dict[str, Any]] = dispatch,
        cancel_aware_handler: Callable[[ClaimedStep, Event], dict[str, Any]] | None = None,
    ) -> None:
        if not 0.1 <= poll_interval_seconds <= 60:
            raise ValueError("poll interval must be between 0.1 and 60 seconds")
        if not poll_interval_seconds <= idle_backoff_max_seconds <= 120:
            raise ValueError("idle backoff must be between poll interval and 120 seconds")
        self.worker = worker
        self.poll_interval_seconds = poll_interval_seconds
        self.idle_backoff_max_seconds = idle_backoff_max_seconds
        self.handler = handler
        self.cancel_aware_handler = cancel_aware_handler

    def run(self, stop: Event) -> None:
        idle_delay = self.poll_interval_seconds
        while not stop.is_set():
            try:
                result = self.worker.run_once(
                    self.handler,
                    cancel_aware_handler=self.cancel_aware_handler,
                )
                if result == "idle":
                    stop.wait(idle_delay)
                    idle_delay = min(self.idle_backoff_max_seconds, idle_delay * 1.5)
                else:
                    idle_delay = self.poll_interval_seconds
                    logger.info("Worker step result: %s", result)
            except Exception:
                logger.exception("Worker iteration failed")
                stop.wait(idle_delay)
                idle_delay = min(self.idle_backoff_max_seconds, idle_delay * 2)


def main() -> None:
    settings = get_settings()
    if not settings.worker_enabled:
        raise SystemExit("Worker disabled. Set SULY_WORKER_ENABLED=true to start it.")
    client = get_supabase_admin_client()
    if client is None:
        raise SystemExit("Worker requires server-only Supabase URL and secret key.")
    worker_id = os.environ.get("SULY_WORKER_ID") or f"suly-worker-{os.getpid()}"
    worker = TaskWorker(client, worker_id, settings.worker_lease_seconds)
    stop = Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("Worker starting: %s", worker_id)
    approval_store = ToolApprovalStore(client)
    WorkerRuntime(
        worker,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        handler=lambda step: dispatch(step, approval_store),
        cancel_aware_handler=lambda step, cancel_event: dispatch_cancel_aware(
            step, cancel_event, approval_store
        ),
    ).run(stop)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
