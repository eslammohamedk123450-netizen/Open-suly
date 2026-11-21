"""Allow-listed, provider-independent task worker runtime.

Only registered operations can execute. No arbitrary Python, shell, browser,
filesystem, or external provider calls are available in this runtime.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from time import monotonic
from threading import Event
from typing import Any, Callable
from uuid import UUID

from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.ai_gateway import generate_reply
from app.services.engine_contract import EngineRequest, EngineResult
from app.services.engine_registry import EngineRegistry
from app.services.agent_manager import AgentManager
from app.services.engine_catalog import build_engine_registry as build_pinned_engine_registry
from app.services.agent_catalog import build_agent_manager as build_catalog_agent_manager
from app.services.hermes_agent import HermesAgentCancelled, run_agent_turn
from app.services.engine_run_store import EngineRunStore
from app.services.engine_run_reconciler import EngineRunReconciler
from app.services.task_worker import ClaimedStep, TaskWorker
from app.services.tool_registry import ToolDefinition, ToolExecutionContext, ToolRegistry
from app.services.tool_approvals import ToolApprovalStore
from app.services.opencode_task_executor import OpenCodeTaskExecutor
from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore
from app.services.opencode_session_store import OpenCodeSessionStore
from app.services.project_workspace_store import ProjectWorkspaceStore
from app.services.runtime_broker_contract import RuntimeLease, TaskScopedRuntimeBroker
from app.services.runtime_provisioner_http import HTTPSRuntimeLeaseProvider

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
        on_event: Callable[[dict[str, str | int | float]], bool | None] | None = None,
        runtime_lease: RuntimeLease | None = None,
    ) -> None:
        # نمرر إشارة الإلغاء وهوية المحاولة وقناة أحداث لا تقبل إلا metadata.
        self.cancel_event = cancel_event
        self.idempotency_key = idempotency_key
        self.on_run_started = on_run_started
        self.on_event = on_event
        self.runtime_lease = runtime_lease

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
            on_event=self.on_event,
            runtime_lease=self.runtime_lease,
            task_id=request.task_id,
            engine_run_id=self.runtime_lease.engine_run_id if self.runtime_lease is not None else None,
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
    on_event: Callable[[dict[str, str | int | float]], bool] | None = None,
    runtime_lease: RuntimeLease | None = None,
) -> EngineRegistry:
    """Build the full pinned engine catalogue with only configured Hermes enabled."""
    settings = get_settings()
    hermes_enabled = bool(
        settings.worker_enabled
        and settings.hermes_agent_enabled
        and runtime_lease is not None
    )
    hermes_adapter = HermesAgentAdapter(
        cancel_event,
        idempotency_key=idempotency_key,
        on_run_started=on_run_started,
        on_event=on_event,
        runtime_lease=runtime_lease,
    )
    return build_pinned_engine_registry({
        "hermes-agent": (hermes_enabled, hermes_adapter),
    })


def build_agent_manager(engines: EngineRegistry) -> AgentManager:
    """Use the canonical SULY role catalogue against the live engine allow-list."""
    return build_catalog_agent_manager(engines)


def hermes_agent_turn(step: ClaimedStep, context: ToolExecutionContext | None = None) -> dict[str, Any]:
    # نتحقق من المدخلات قبل إنشاء أي سجل تشغيل خارجي.
    prompt = step.input.get("prompt")
    if not isinstance(prompt, str):
        raise ValueError("hermes.agent.turn requires a string input.prompt")
    settings = get_settings()
    runtime_broker = context.runtime_broker if context is not None else None
    if (
        not settings.worker_enabled
        or not settings.hermes_agent_enabled
        or runtime_broker is None
    ):
        raise RuntimeError("hermes_task_runtime_unavailable")

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

    def persist_engine_event(event: dict[str, str | int | float]) -> bool:
        # نسجل metadata فقط؛ لا نطبع محتوى الحدث أو أي نص من المحرك.
        try:
            persisted = run_store.append_event(run_id, step, event)
        except Exception:
            logger.warning(
                "Hermes progress event persistence failed for run %s (event=%s)",
                run_id,
                event.get("event", "unknown"),
            )
            return False
        if not persisted:
            logger.warning(
                "Hermes progress event rejected after lease loss for run %s (event=%s)",
                run_id,
                event.get("event", "unknown"),
            )
        return persisted

    try:
        runtime_lease = runtime_broker.acquire(
            str(step.task_id), str(run_id), "hermes-agent"
        )
    except Exception as exc:
        run_store.finish(run_id, step, "failed", "hermes_runtime_acquire_failed")
        raise RuntimeError("hermes_task_runtime_acquire_failed") from exc

    try:
        registry = build_engine_registry(
            cancel_event,
            idempotency_key=f"suly-{run_id}",
            on_run_started=lambda upstream_id: run_store.attach_upstream_run_id(
                run_id, step, upstream_id
            ),
            on_event=persist_engine_event,
            runtime_lease=runtime_lease,
        )
        manager = build_agent_manager(registry)
        try:
            route = manager.route("general-agent", "agent.general")
            selected_engine = route.engines[0]
        except (ValueError, RuntimeError):
            run_store.finish(run_id, step, "failed", "agent_route_unavailable")
            raise

        try:
            result = registry.execute(selected_engine.engine_id, request)
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
    finally:
        try:
            released = runtime_broker.release(runtime_lease)
            if not released:
                logger.warning("Hermes task runtime release was not confirmed for attempt %s", run_id)
        except Exception:
            logger.warning("Hermes task runtime cleanup failed for attempt %s", run_id)


def dispatch_cancel_aware(
    step: ClaimedStep,
    cancel_event: Event,
    approval_store: ToolApprovalStore | None = None,
    runtime_broker: TaskScopedRuntimeBroker | None = None,
) -> dict[str, Any]:
    """Refuse to start an operation after the worker loses its lease or is cancelled.

    The worker still owns the authoritative lease check before checkpointing;
    this event is a cooperative stop signal, never an authorization grant.
    """
    if cancel_event.is_set():
        raise RuntimeError("task_execution_cancelled")
    return dispatch(step, approval_store, cancel_event=cancel_event, runtime_broker=runtime_broker)


def opencode_task_run(step: ClaimedStep, context: ToolExecutionContext | None = None) -> dict[str, Any]:
    """تنفيذ مهمة برمجية عبر OpenCode داخل runtime منفصل ومربوط بملكية المهمة."""
    settings = get_settings()
    broker = context.runtime_broker if context is not None else None
    run_store = context.engine_run_store if context is not None else None
    cancel_event = context.cancel_event if context is not None else None
    project_id = step.input.get("project_id")
    prompt = step.input.get("prompt")
    title = step.input.get("title", step.title)
    if (
        not settings.worker_enabled or not settings.opencode_enabled
        or broker is None or run_store is None
    ):
        raise RuntimeError("opencode_engine_disabled_or_unavailable")
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("task_execution_cancelled")
    if not isinstance(project_id, str):
        raise ValueError("opencode_project_id_required")
    try:
        project_uuid = UUID(project_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("opencode_project_id_invalid") from exc
    if str(project_uuid) != project_id:
        raise ValueError("opencode_project_id_invalid")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32_000:
        raise ValueError("opencode_prompt_invalid")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        raise ValueError("opencode_title_invalid")

    # نبدأ سجل المحرك من RPC المقيد بالـlease قبل تشغيل OpenCode.
    engine_run_id = run_store.start(step, "opencode")
    client = get_supabase_admin_client()
    if client is None:
        run_store.finish(engine_run_id, step, "failed", "opencode_store_unavailable")
        raise RuntimeError("opencode_store_unavailable")
    executor = OpenCodeTaskExecutor(
        workspace_store=ProjectWorkspaceStore(client),
        session_store=OpenCodeSessionStore(client),
        runtime_broker=broker,
        lifecycle_store=OpenCodeLifecycleStore(client),
    )
    try:
        result = executor.execute(
            user_id=str(step.user_id), project_id=project_id, task_id=str(step.task_id),
            engine_run_id=str(engine_run_id), prompt=prompt.strip(), title=title.strip(),
            cancel_event=cancel_event,
        )
        if cancel_event is not None and cancel_event.is_set():
            run_store.finish(engine_run_id, step, "cancelled")
            raise RuntimeError("opencode_task_cancelled")
        if not run_store.finish(engine_run_id, step, "succeeded"):
            raise RuntimeError("opencode_engine_run_lease_lost")
        changes = result.get("changes", {})
        task_run = result.get("task_run", {})
        change_set = result.get("change_set", {})
        session = result.get("session", {})
        return {
            "operation": "opencode.task.run",
            "engine_run_id": str(engine_run_id),
            "opencode_run_id": task_run.get("id"),
            "session_record_id": session.get("id"),
            "change_set_id": change_set.get("id"),
            "status": task_run.get("status", "review_ready"),
            "changed_count": changes.get("changed_count", 0),
            "requires_review": True,
        }
    except Exception:
        try:
            run_store.finish(engine_run_id, step, "failed", "opencode_execution_failed")
        except Exception:
            logger.warning("OpenCode engine-run failure status was not persisted")
        raise


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
        name="opencode.task.run",
        description="Run one bounded coding prompt in an isolated OpenCode task runtime and return a reviewable change set",
        permission_scope="engine.opencode.run",
        allowed_input_fields=frozenset({"project_id", "prompt", "title"}),
        required_input_fields=frozenset({"project_id", "prompt"}),
        max_input_bytes=48_000,
        handler=opencode_task_run,
        requires_approval=True,
        max_output_bytes=16_000,
        supports_cancellation=True,
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
    runtime_broker: TaskScopedRuntimeBroker | None = None,
) -> dict[str, Any]:
    # Fetch persisted consent immediately before execution so revocation takes
    # effect on the next attempt; never derive grants from task payloads.
    scopes = approval_store.active_scopes(str(step.user_id)) if approval_store else frozenset()
    tool = TOOL_REGISTRY.get(step.input.get("operation")) if isinstance(step.input, dict) else None
    if tool is not None and tool.requires_approval and tool.permission_scope not in scopes:
        raise PermissionError(f"tool_approval_required:{tool.permission_scope}")
    run_store = None
    if step.input.get("operation") in {"hermes.agent.turn", "opencode.task.run"}:
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
            runtime_broker=runtime_broker,
        ),
    )


class WorkerRuntime:
    def __init__(
        self,
        worker: TaskWorker,
        *,
        poll_interval_seconds: float = 2.0,
        idle_backoff_max_seconds: float = 15.0,
        handler: Callable[[ClaimedStep], dict[str, Any]] | None = None,
        cancel_aware_handler: Callable[[ClaimedStep, Event], dict[str, Any]] | None = None,
        reconciler: EngineRunReconciler | None = None,
        reconcile_interval_seconds: int = 30,
        runtime_broker: TaskScopedRuntimeBroker | None = None,
    ) -> None:
        if not 0.1 <= poll_interval_seconds <= 60:
            raise ValueError("poll interval must be between 0.1 and 60 seconds")
        if not poll_interval_seconds <= idle_backoff_max_seconds <= 120:
            raise ValueError("idle backoff must be between poll interval and 120 seconds")
        self.worker = worker
        self.poll_interval_seconds = poll_interval_seconds
        self.idle_backoff_max_seconds = idle_backoff_max_seconds
        self.runtime_broker = runtime_broker
        self.handler = handler or (lambda step: dispatch(step, runtime_broker=runtime_broker))
        self.cancel_aware_handler = cancel_aware_handler
        if handler is None and cancel_aware_handler is None:
            self.cancel_aware_handler = lambda step, cancel_event: dispatch_cancel_aware(
                step, cancel_event, runtime_broker=runtime_broker
            )
        if not 10 <= reconcile_interval_seconds <= 600:
            raise ValueError("reconcile interval must be between 10 and 600 seconds")
        self.reconciler = reconciler
        self.reconcile_interval_seconds = reconcile_interval_seconds
        self.runtime_broker = runtime_broker

    def run(self, stop: Event) -> None:
        idle_delay = self.poll_interval_seconds
        next_reconcile_at = monotonic()
        while not stop.is_set():
            if self.reconciler is not None and monotonic() >= next_reconcile_at:
                try:
                    reconciled = self.reconciler.run_once()
                    if reconciled:
                        logger.info("Confirmed external engine stops: %s", reconciled)
                except Exception:
                    # لا نطبع تفاصيل استثناءات RPC أو المحرك في سجل التشغيل العام.
                    logger.error("Engine stop reconciliation iteration failed")
                next_reconcile_at = monotonic() + self.reconcile_interval_seconds
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
            except Exception as exc:
                # Exception messages may contain prompts, provider payloads,
                # database URLs, or credentials. Log only the exception type.
                logger.error(
                    "Worker iteration failed (exception_type=%s)",
                    type(exc).__name__,
                )
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
    # Per-task Hermes runtimes are released through their lease. Crash recovery
    # still depends on the provisioner's TTL until runtime identity is persisted
    # and a lease-recovery stop reconciler is implemented.
    reconciler = None
    runtime_broker = None
    runtime_provider = None
    if settings.opencode_enabled or settings.hermes_agent_enabled:
        configured = (
            settings.runtime_provisioner_url,
            settings.runtime_provisioner_token,
            settings.runtime_provisioner_allowed_origins,
        )
        if not all(configured):
            raise SystemExit("Isolated engine runtime configuration is incomplete.")
        allowed_origins = frozenset(settings.runtime_provisioner_allowed_origins)
        runtime_provider = HTTPSRuntimeLeaseProvider(
            base_url=settings.runtime_provisioner_url,
            bearer_token=settings.runtime_provisioner_token.get_secret_value(),
            allowed_origins=allowed_origins,
            timeout_seconds=settings.runtime_provisioner_timeout_seconds,
        )
        runtime_broker = TaskScopedRuntimeBroker(
            runtime_provider, allowed_origins=allowed_origins
        )
    WorkerRuntime(
        worker,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        handler=lambda step: dispatch(step, approval_store),
        cancel_aware_handler=lambda step, cancel_event: dispatch_cancel_aware(
            step, cancel_event, approval_store, runtime_broker
        ),
        reconciler=reconciler,
        reconcile_interval_seconds=settings.engine_reconciler_interval_seconds,
        runtime_broker=runtime_broker,
    ).run(stop)
    if runtime_provider is not None:
        runtime_provider.close()
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
