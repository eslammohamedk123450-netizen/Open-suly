"""Owner-scoped orchestration from SULY project snapshot to OpenCode results.

This service deliberately returns a reviewable diff payload; it never overwrites
canonical project files automatically.
"""
from __future__ import annotations

from typing import Any

from app.services.opencode_session_store import OpenCodeSessionStore
from app.services.project_workspace_store import ProjectWorkspaceStore
from app.services.runtime_broker_contract import TaskScopedRuntimeBroker
from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore


class OpenCodeTaskExecutor:
    def __init__(
        self,
        *,
        workspace_store: ProjectWorkspaceStore,
        session_store: OpenCodeSessionStore,
        runtime_broker: TaskScopedRuntimeBroker,
        lifecycle_store: OpenCodeLifecycleStore | None = None,
    ) -> None:
        self._workspace = workspace_store
        self._sessions = session_store
        self._broker = runtime_broker
        self._lifecycle = lifecycle_store

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
        lifecycle_run = None
        if self._lifecycle is not None:
            lifecycle_run = self._lifecycle.create_run(
                user_id=user_id, project_id=project_id, task_id=task_id,
                engine_run_id=engine_run_id, workspace_revision=snapshot["revision"],
            )
            self._lifecycle.append_event(
                user_id=user_id, run_id=lifecycle_run["id"], sequence=1,
                event_type="task.started", payload={"task_id": task_id},
            )
        try:
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
            if lifecycle_run is not None and isinstance(execution.get("runtime_id"), str):
                self._lifecycle.set_runtime(
                    user_id=user_id, run_id=lifecycle_run["id"],
                    runtime_id=execution["runtime_id"], session_id=execution["session_id"],
                    status="running",
                )
        except Exception:
            if lifecycle_run is not None:
                self._lifecycle.update_status(
                    user_id=user_id, run_id=lifecycle_run["id"], status="failed",
                    error_code="opencode_execution_failed",
                )
                self._lifecycle.append_event(
                    user_id=user_id, run_id=lifecycle_run["id"], sequence=2,
                    event_type="task.failed", payload={"code": "opencode_execution_failed"},
                )
            raise

        session = self._sessions.register(
            user_id=user_id,
            project_id=project_id,
            upstream_session_id=execution["session_id"],
            title=title,
            task_id=task_id,
            engine_run_id=engine_run_id,
            workspace_revision=snapshot["revision"],
        )
        change_set = None
        if lifecycle_run is not None:
            original_paths = {item["path"] for item in snapshot["files"]}
            changes = []
            for item in results.get("changed_files", []):
                if not isinstance(item, dict):
                    continue
                action = "update" if item.get("path") in original_paths else "create"
                changes.append({
                    "action": action, "path": item.get("path"),
                    "content": item.get("content"), "sha256": item.get("sha256"),
                })
            for path in results.get("deleted_paths", []):
                changes.append({"action": "delete", "path": path})
            change_set = self._lifecycle.create_change_set(
                user_id=user_id, project_id=project_id, run_id=lifecycle_run["id"],
                base_revision=snapshot["revision"], changes=changes,
            )
            self._lifecycle.update_status(
                user_id=user_id, run_id=lifecycle_run["id"], status="review_ready",
            )
            self._lifecycle.append_event(
                user_id=user_id, run_id=lifecycle_run["id"], sequence=2,
                event_type="changes.collected",
                payload={"change_set_id": change_set["id"], "changed_count": len(changes)},
            )
        return {
            "session": session,
            "task_run": lifecycle_run,
            "change_set": change_set,
            "workspace_revision": snapshot["revision"],
            "execution": execution,
            "changes": {
                "changed_files": results.get("changed_files", []),
                "deleted_paths": results.get("deleted_paths", []),
                "changed_count": results.get("changed_count", 0),
            },
            "requires_review": True,
        }
