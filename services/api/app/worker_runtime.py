"""Allow-listed, provider-independent task worker runtime.

Only explicitly registered operations can execute. No arbitrary Python, shell,
browser, or external provider calls are available in this runtime.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from threading import Event
from typing import Any, Callable

from app.core.config import get_settings
from app.core.supabase import get_supabase_admin_client
from app.services.task_worker import ClaimedStep, TaskWorker

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


HANDLERS: dict[str, Callable[[ClaimedStep], dict[str, Any]]] = {
    "text.analyze": text_analyze,
}


def dispatch(step: ClaimedStep) -> dict[str, Any]:
    operation = step.input.get("operation")
    if not isinstance(operation, str) or operation not in HANDLERS:
        raise ValueError("unsupported_operation: task step must name an allow-listed operation")
    return HANDLERS[operation](step)


class WorkerRuntime:
    def __init__(
        self,
        worker: TaskWorker,
        *,
        poll_interval_seconds: float = 2.0,
        idle_backoff_max_seconds: float = 15.0,
    ) -> None:
        if not 0.1 <= poll_interval_seconds <= 60:
            raise ValueError("poll interval must be between 0.1 and 60 seconds")
        if not poll_interval_seconds <= idle_backoff_max_seconds <= 120:
            raise ValueError("idle backoff must be between poll interval and 120 seconds")
        self.worker = worker
        self.poll_interval_seconds = poll_interval_seconds
        self.idle_backoff_max_seconds = idle_backoff_max_seconds

    def run(self, stop: Event) -> None:
        idle_delay = self.poll_interval_seconds
        while not stop.is_set():
            try:
                result = self.worker.run_once(dispatch)
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
    logger.info("SULY worker starting: %s", worker_id)
    WorkerRuntime(
        worker,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
    ).run(stop)
    logger.info("SULY worker stopped")


if __name__ == "__main__":
    main()
