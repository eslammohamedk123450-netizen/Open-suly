from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.opencode_task_executor import OpenCodeTaskExecutor


class Workspace:
    def snapshot(self, *, user_id, project_id):
        return {
            "revision": "a" * 64,
            "files": [
                {"path": "src/main.py", "content": "print('before')", "sha256": "b" * 64},
                {"path": "old.py", "content": "legacy = True", "sha256": "c" * 64},
            ],
        }


class Broker:
    def __init__(self):
        self.calls = []

    def run_task(self, task_id, run_id, engine_id, *, files, prompt, title, on_lease_acquired=None, on_session_created=None):
        self.calls.append((task_id, run_id, engine_id, files, prompt, title))
        return {
            "execution": {"session_id": "sesABC123", "result": {"ok": True}},
            "results": {
                "changed_files": [{"path": "src/main.py", "content": "print('after')"}],
                "deleted_paths": ["old.py"],
                "changed_count": 1,
            },
        }


class Sessions:
    def register(self, **kwargs):
        self.kwargs = kwargs
        return {"id": "session-row", "upstream_session_id": kwargs["upstream_session_id"]}


def test_executor_sends_project_snapshot_and_returns_reviewable_changes():
    user_id, project_id, task_id, run_id = (str(uuid4()) for _ in range(4))
    broker, sessions = Broker(), Sessions()
    executor = OpenCodeTaskExecutor(
        workspace_store=Workspace(), session_store=sessions, runtime_broker=broker,
    )
    result = executor.execute(
        user_id=user_id, project_id=project_id, task_id=task_id,
        engine_run_id=run_id, prompt="Add a feature",
    )
    assert broker.calls[0][2] == "opencode"
    assert broker.calls[0][3][0]["path"] == "src/main.py"
    assert result["changes"]["changed_files"][0]["content"] == "print('after')"
    assert result["changes"]["deleted_paths"] == ["old.py"]
    assert result["requires_review"] is True
    assert sessions.kwargs["workspace_revision"] == "a" * 64


class Lifecycle:
    def __init__(self):
        self.calls = []
    def create_run(self, **kwargs):
        self.calls.append(("create_run", kwargs))
        return {"id": str(uuid4()), "status": "queued"}
    def append_event(self, **kwargs):
        self.calls.append(("event", kwargs))
        return True
    def create_change_set(self, **kwargs):
        self.calls.append(("change_set", kwargs))
        return {"id": str(uuid4()), "status": "review_ready"}
    def update_status(self, **kwargs):
        self.calls.append(("status", kwargs))
        return True
    def set_runtime(self, **kwargs):
        self.calls.append(("runtime", kwargs))
        return True


def test_executor_persists_run_and_reviewable_change_set():
    import hashlib
    user_id, project_id, task_id, run_id = (str(uuid4()) for _ in range(4))
    broker, sessions, lifecycle = Broker(), Sessions(), Lifecycle()
    changed = "print('after')"
    broker.run_task = lambda *args, **kwargs: {
        "execution": {"session_id": "sesABC123"},
        "results": {
            "changed_files": [{
                "path": "src/main.py", "content": changed,
                "sha256": hashlib.sha256(changed.encode()).hexdigest(),
            }],
            "deleted_paths": ["old.py"], "changed_count": 1,
        },
    }
    executor = OpenCodeTaskExecutor(
        workspace_store=Workspace(), session_store=sessions,
        runtime_broker=broker, lifecycle_store=lifecycle,
    )
    result = executor.execute(
        user_id=user_id, project_id=project_id, task_id=task_id,
        engine_run_id=run_id, prompt="Change the file",
    )
    assert result["task_run"]["status"] == "review_ready"
    assert result["change_set"]["status"] == "review_ready"
    assert result["requires_review"] is True
    change_call = next(call for call in lifecycle.calls if call[0] == "change_set")
    assert change_call[1]["base_revision"] == "a" * 64
    assert change_call[1]["changes"][0]["action"] == "update"
    assert change_call[1]["changes"][1]["action"] == "delete"
    assert change_call[1]["changes"][1]["path"] == "old.py"
    assert "--- a/src/main.py" in change_call[1]["changes"][0]["diff"]
    assert "+++ b/src/main.py" in change_call[1]["changes"][0]["diff"]
    assert any(call[0] == "event" and call[1]["event_type"] == "changes.collected" for call in lifecycle.calls)


def test_executor_rejects_runtime_result_with_forged_content_digest():
    user_id, project_id, task_id, run_id = (str(uuid4()) for _ in range(4))
    broker, sessions, lifecycle = Broker(), Sessions(), Lifecycle()
    broker.run_task = lambda *args, **kwargs: {
        "execution": {"session_id": "sesABC123"},
        "results": {
            "changed_files": [{
                "path": "src/main.py", "content": "print('tampered')",
                "sha256": "0" * 64,
            }],
            "deleted_paths": [], "changed_count": 1,
        },
    }
    broker.release_attempt = lambda *_args: True
    executor = OpenCodeTaskExecutor(
        workspace_store=Workspace(), session_store=sessions,
        runtime_broker=broker, lifecycle_store=lifecycle,
    )

    with pytest.raises(ValueError, match="opencode_result_digest_mismatch"):
        executor.execute(
            user_id=user_id, project_id=project_id, task_id=task_id,
            engine_run_id=run_id, prompt="Change the file",
        )

    assert not any(call[0] == "change_set" for call in lifecycle.calls)
    assert any(
        call[0] == "status" and call[1]["status"] == "failed"
        for call in lifecycle.calls
    )


def test_executor_persists_runtime_id_immediately_when_lease_is_acquired():
    from types import SimpleNamespace

    user_id, project_id, task_id, run_id = (str(uuid4()) for _ in range(4))
    lifecycle = Lifecycle()
    runtime_id = str(uuid4())

    class CallbackBroker(Broker):
        def run_task(self, task_id, run_id, engine_id, *, files, prompt, title, on_lease_acquired=None, on_session_created=None):
            assert callable(on_lease_acquired)
            assert callable(on_session_created)
            lease = SimpleNamespace(runtime_id=runtime_id)
            on_lease_acquired(lease)
            on_session_created(lease, "sesABC123")
            return {
                "execution": {"runtime_id": runtime_id, "session_id": "sesABC123"},
                "results": {"changed_files": [], "deleted_paths": [], "changed_count": 0},
            }

    executor = OpenCodeTaskExecutor(
        workspace_store=Workspace(), session_store=Sessions(),
        runtime_broker=CallbackBroker(), lifecycle_store=lifecycle,
    )
    executor.execute(
        user_id=user_id, project_id=project_id, task_id=task_id,
        engine_run_id=run_id, prompt="Run a task",
    )

    runtime_calls = [call[1] for call in lifecycle.calls if call[0] == "runtime"]
    assert runtime_calls[0]["runtime_id"] == runtime_id
    assert runtime_calls[0]["session_id"] is None
    assert runtime_calls[0]["status"] == "provisioning"
    assert runtime_calls[1]["session_id"] == "sesABC123"
    assert runtime_calls[1]["status"] == "running"
