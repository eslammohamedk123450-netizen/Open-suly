from threading import Event
from uuid import UUID

import pytest

from app.services.task_worker import ClaimedStep
from app.worker_runtime import WorkerRuntime, dispatch, text_analyze


def make_step(input_data):
    return ClaimedStep(
        step_id=UUID("00000000-0000-0000-0000-000000000001"),
        task_id=UUID("00000000-0000-0000-0000-000000000002"),
        user_id=UUID("00000000-0000-0000-0000-000000000003"),
        step_key="analyze",
        title="Analyze text",
        description="",
        input=input_data,
        attempt_count=1,
        max_attempts=3,
        lease_token=UUID("00000000-0000-0000-0000-000000000004"),
        lease_expires_at="2026-11-20T12:00:00+00:00",
    )


def test_text_analyze_returns_bounded_deterministic_metrics():
    result = dispatch(make_step({"operation": "text.analyze", "text": "one two\nthree"}))
    assert result["word_count"] == 3
    assert result["character_count"] == 13
    assert result["line_count"] == 2


def test_worker_rejects_unregistered_operations():
    with pytest.raises(ValueError, match="unsupported_operation"):
        dispatch(make_step({"operation": "shell.exec", "command": "whoami"}))


def test_text_analyze_requires_string_input():
    with pytest.raises(ValueError, match="requires a string"):
        text_analyze(make_step({"operation": "text.analyze", "text": 123}))


def test_runtime_stops_without_claiming_work_after_stop_signal():
    class NeverCalledWorker:
        def run_once(self, _handler):
            raise AssertionError("stop should be checked before the first iteration")

    stop = Event()
    stop.set()
    runtime = WorkerRuntime(NeverCalledWorker())
    runtime.run(stop)


def test_runtime_rejects_unsafe_poll_intervals():
    with pytest.raises(ValueError):
        WorkerRuntime(object(), poll_interval_seconds=0)
