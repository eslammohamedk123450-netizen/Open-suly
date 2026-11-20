from __future__ import annotations

from uuid import uuid4

from app.services.opencode_task_executor import OpenCodeTaskExecutor


class Workspace:
    def snapshot(self, *, user_id, project_id):
        return {
            "revision": "a" * 64,
            "files": [{"path": "src/main.py", "content": "print('before')", "sha256": "b" * 64}],
        }


class Broker:
    def __init__(self):
        self.calls = []

    def run_task(self, task_id, run_id, engine_id, *, files, prompt, title):
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
