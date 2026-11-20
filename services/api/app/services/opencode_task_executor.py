"""Owner-scoped orchestration from SULY project snapshot to OpenCode results.

This service deliberately returns a reviewable diff payload; it never overwrites
canonical project files automatically.
"""
from __future__ import annotations

from typing import Any

from app.services.opencode_session_store import OpenCodeSessionStore
from app.services.project_workspace_store import ProjectWorkspaceStore
from app.services.runtime_broker_contract import TaskScopedRuntimeBroker


class OpenCodeTaskExecutor:
    def __init__(
        self,
        *,
        workspace_store: ProjectWorkspaceStore,
        session_store: OpenCodeSessionStore,
        runtime_broker: TaskScopedRuntimeBroker,
    ) -> None:
        self._workspace = workspace_store
        self._sessions = session_store
        self._broker = runtime_broker

    def execute(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
        engine_run_id: str,
        prompt: str,
        title: str = "SULY coding task",
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32_000:
            raise ValueError("opencode_prompt_invalid")
        snapshot = self._workspace.snapshot(user_id=user_id, project_id=project_id)
        result = self._broker.run_task(
            task_id,
            engine_run_id,
            "opencode",
            files=snapshot["files"],
            prompt=prompt,
            title=title,
        )
        execution = result.get("execution")
        results = result.get("results")
        if not isinstance(execution, dict) or not isinstance(execution.get("session_id"), str):
            raise RuntimeError("opencode_execution_result_invalid")
        if not isinstance(results, dict) or not isinstance(results.get("changed_files"), list):
            raise RuntimeError("opencode_workspace_result_invalid")
        session = self._sessions.register(
            user_id=user_id,
            project_id=project_id,
            upstream_session_id=execution["session_id"],
            title=title,
            task_id=task_id,
            engine_run_id=engine_run_id,
            workspace_revision=snapshot["revision"],
        )
        return {
            "session": session,
            "workspace_revision": snapshot["revision"],
            "execution": execution,
            "changes": {
                "changed_files": results.get("changed_files", []),
                "deleted_paths": results.get("deleted_paths", []),
                "changed_count": results.get("changed_count", 0),
            },
            "requires_review": True,
        }
