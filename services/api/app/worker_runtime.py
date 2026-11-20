"""Allow-listed, provider-independent task worker runtime.

Only registered operations can execute. No arbitrary Python, shell, browser,
filesystem, or external provider calls are available in this runtime.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from threading import Event
from typing import Any, Callable

from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.ai_gateway import generate_reply
from app.services.engine_contract import EngineRequest, EngineResult
from app.services.engine_registry import EngineDefinition, EngineRegistry
from app.services.hermes_agent import HermesAgentCancelled, run_agent_turn
from app.services.engine_run_store import EngineRunStore
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


def ai_respond(step: ClaimedStep) -> dict[str, Any]:
    prompt = step.input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise ValueError("ai.respond requires a prompt containing 1–20000 characters")
    reply = asyncio.run(generate_reply([{"role": "user", "content": prompt.strip()}]))
    return {"operation": "ai.respond", "content": reply}


class HermesAgentAdapter:
    """Narrow adapter to the separately hosted Hermes bridge."""

    def __init__(
        self,
        cancel_event: Event | None = None,
        *,
        idempotency_key: str,
        on_run_started: Callable[[str], bool],
    ) -> None:
        # نمرر إشارة الإلغاء ومفتاح المحاولة ودالة حفظ معرف Hermes الخارجي.
        self.cancel_event = cancel_event
        self.idempotency_key = idempotency_key
        self.on_run_started = on_run_started

    def execute(self, request: EngineRequest) -> EngineResult:
        prompt = request.input_payload.get("prompt")
        if not isinstance(prompt, str):
            raise ValueError("hermes_adapter_prompt_required")
        result = run_agent_turn(
            prompt,
            timeout_seconds=request.timeout_seconds,
            cancel_event=self.cancel_event,
            idempotency_key=self.idempotency_key,
            on_run_started=self.on_run_started,
        )
        if not isinstance(result, dict) or not isinstance(result.get("content"), str):
            raise ValueError("hermes_adapter_invalid_response")
        return EngineResult(
            engine_id="hermes-agent",
            output={"engine": result.get("engine", "hermes-agent"), "content": result["content"]},
        )


def build_engine_registry(
    cancel_event: Event | None = None,
    *,
    idempotency_key: str,
    on_run_started: Callable[[str], bool],
) -> EngineRegistry:
    """Build the server-configured allow-list; external engines default off."""
    settings = get_settings()
    return EngineRegistry([
        EngineDefinition(
            engine_id="hermes-agent",
            display_name="Hermes Agent",
            capabilities=frozenset({"agent.general"}),
            enabled=settings.hermes_agent_enabled,
            requires_approval=True,
            max_input_bytes=20_100,
            max_output_bytes=52_000,
            max_timeout_seconds=300,
            adapter=HermesAgentAdapter(\n                cancel_event,\n                idempotency_key=idempotency_key,\n                on_run_started=on_run_started,\n            ),
        )
    ])


def hermes_agent_turn(step: ClaimedStep, context: ToolExecutionContext | None = None) -> dict[str, Any]:
    # نتحقق من المدخلات قبل إنشاء أي سجل تشغيل خارجي.
    prompt = step.input.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("hermes.agent.turn requires a string input.prompt")
    settings = get_settings()
    if not settings.hermes_agent_enabled:
        raise RuntimeError("engine_disabled")

    # نجهز طلب المحرك بحد أقصى زمني معروف من إعدادات الخادم.
    request = EngineRequest(
        task_id=str(step.task_id),
        capability="agent.general",
        input_payload={"prompt": prompt},
        timeout_seconds=max(1, min(300, int(settings.hermes_agent_timeout_seconds))),
    )
    cancel_event = context.cancel_event if context is not None else None
    run_store = context.engine_run_store if context is not None else None
    if run_store is None:
        raise RuntimeError("engine_run_store_unavailable")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("task_execution_cancelled")

    # ننشئ سجل المحاولة أولًا ليصبح UUID الخاص به مفتاح idempotency ثابتًا لدى Hermes.
    run_id = run_store.start(step, "hermes-agent")
    registry = build_engine_registry(
        cancel_event,
        idempotency_key=f"suly-{run_id}",
        on_run_started=lambda upstream_id: run_store.attach_upstream_run_id(
            run_id, step, upstream_id
        ),
    )
    definition = registry.get("hermes-agent")
    if definition is None or not definition.enabled:
        run_store.finish(run_id, step, "failed", "engine_disabled")
        raise RuntimeError("engine_disabled")

    try:
        # لا نعتبر بدء Hermes ناجحًا حتى نحفظ معرفه الخارجي تحت lease الحالي.
        result = registry.execute("hermes-agent", request)
    except HermesAgentCancelled:
        run_store.finish(run_id, step, "cancelled")
        raise
    except Exception:
        run_store.finish(run_id, step, "failed", "engine_execution_failed")
        raise
    if not run_store.finish(run_id, step, "succeeded"):
        raise RuntimeError("engine_run_lease_lost")
    return {
        "operation": "hermes.agent.turn",
        "engine": result.output["engine"],
        "content": result.output["content"],
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
    return dispatch(step, approval_store, cancel_event=cancel_event)


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
        name="ai.respond",
        description="Generate one bounded response through the configured SULY AI provider",
        permission_scope="ai.provider.run",
        allowed_input_fields=frozenset({"prompt"}),
        required_input_fields=frozenset({"prompt"}),
        max_input_bytes=20_100,
        handler=ai_respond,
        requires_approval=True,
        max_output_bytes=52_000,
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
        supports_cancellation=True,
    ))
    return registry


TOOL_REGISTRY = build_tool_registry()


def dispatch(
    step: ClaimedStep,
    approval_store: ToolApprovalStore | None = None,
    *,
    cancel_event: Event | None = None,
) -> dict[str, Any]:
    # Fetch persisted consent immediately before execution so revocation takes
    # effect on the next attempt; never derive grants from task payloads.
    scopes = approval_store.active_scopes(str(step.user_id)) if approval_store else frozenset()
    tool = TOOL_REGISTRY.get(step.input.get("operation")) if isinstance(step.input, dict) else None
    if tool is not None and tool.requires_approval and tool.permission_scope not in scopes:
        raise PermissionError(f"tool_approval_required:{tool.permission_scope}")
    run_store = None
    if step.input.get("operation") == "hermes.agent.turn":
        client = get_supabase_admin_client()
        if client is None:
            raise RuntimeError("engine_run_store_unavailable")
        run_store = EngineRunStore(client)
    return TOOL_REGISTRY.execute(
        step,
        ToolExecutionContext(
            approved_scopes=scopes,
            cancel_event=cancel_event,
            engine_run_store=run_store,
        ),
    )


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
