"""Owner-scoped orchestration from SULY project snapshot to OpenCode results.

This service deliberately returns a reviewable diff payload; it never overwrites
canonical project files automatically.
"""
from __future__ import annotations

from typing import Any
from difflib import unified_diff
import hashlib

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
            lease_callback = None
            if lifecycle_run is not None:
                def persist_runtime_lease(lease) -> None:
                    persisted = self._lifecycle.set_runtime(
                        user_id=user_id,
                        run_id=lifecycle_run["id"],
                        runtime_id=lease.runtime_id,
                        session_id=None,
                        status="provisioning",
                    )
                    if not persisted:
                        raise RuntimeError("opencode_runtime_persistence_failed")
                lease_callback = persist_runtime_lease
            result = self._broker.run_task(
                task_id,
                engine_run_id,
                "opencode",
                files=snapshot["files"],
                prompt=prompt,
                title=title,
                on_lease_acquired=lease_callback,
            )
            execution = result.get("execution")
            results = result.get("results")
            if not isinstance(execution, dict) or not isinstance(execution.get("session_id"), str):
                raise RuntimeError("opencode_execution_result_invalid")
            if not isinstance(results, dict) or not isinstance(results.get("changed_files"), list):
                raise RuntimeError("opencode_workspace_result_invalid")
            if lifecycle_run is not None and isinstance(execution.get("runtime_id"), str):
                persisted = self._lifecycle.set_runtime(
                    user_id=user_id, run_id=lifecycle_run["id"],
                    runtime_id=execution["runtime_id"], session_id=execution["session_id"],
                    status="running",
                )
                if not persisted:
                    raise RuntimeError("opencode_session_persistence_failed")
        except Exception:
            self._broker.release_attempt(task_id, engine_run_id, "opencode")
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

        try:
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
                original_by_path = {item["path"]: item["content"] for item in snapshot["files"]}
                changed_files = results.get("changed_files", [])
                deleted_paths = results.get("deleted_paths", [])
                if (
                    not isinstance(changed_files, list) or len(changed_files) > 500
                    or not isinstance(deleted_paths, list) or len(deleted_paths) > 500
                ):
                    raise ValueError("opencode_result_file_count_invalid")
                changes = []
                seen_paths: set[str] = set()
                for item in changed_files:
                    if not isinstance(item, dict):
                        raise ValueError("opencode_result_file_invalid")
                    path = ProjectWorkspaceStore._path(item.get("path"))
                    new_content = item.get("content")
                    if not isinstance(new_content, str) or len(new_content.encode("utf-8")) > 256 * 1024:
                        raise ValueError("opencode_result_content_invalid")
                    if path in seen_paths:
                        raise ValueError("opencode_result_duplicate_path")
                    seen_paths.add(path)
                    digest = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
                    supplied_digest = item.get("sha256")
                    if supplied_digest is not None and supplied_digest != digest:
                        raise ValueError("opencode_result_digest_mismatch")
                    old_content = original_by_path.get(path, "")
                    action = "update" if path in original_by_path else "create"
                    if action == "update" and old_content == new_content:
                        continue
                    diff = "".join(unified_diff(
                        old_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{path}" if action == "update" else "/dev/null",
                        tofile=f"b/{path}",
                    ))
                    changes.append({
                        "action": action, "path": path,
                        "content": new_content, "sha256": digest,
                        "diff": diff[:256 * 1024],
                    })
                for raw_path in deleted_paths:
                    path = ProjectWorkspaceStore._path(raw_path)
                    if path in seen_paths or path not in original_by_path:
                        raise ValueError("opencode_result_deleted_path_invalid")
                    seen_paths.add(path)
                    old_content = original_by_path[path]
                    diff = "".join(unified_diff(
                        old_content.splitlines(keepends=True), [],
                        fromfile=f"a/{path}", tofile="/dev/null",
                    ))
                    changes.append({"action": "delete", "path": path, "diff": diff[:256 * 1024]})
                change_set = self._lifecycle.create_change_set(
                    user_id=user_id, project_id=project_id, run_id=lifecycle_run["id"],
                    base_revision=snapshot["revision"], changes=changes,
                )
                self._lifecycle.update_status(
                    user_id=user_id, run_id=lifecycle_run["id"], status="review_ready",
                )
                lifecycle_run["status"] = "review_ready"
                self._lifecycle.append_event(
                    user_id=user_id, run_id=lifecycle_run["id"], sequence=2,
                    event_type="changes.collected",
                    payload={"change_set_id": change_set["id"], "changed_count": len(changes)},
                )
    
        except Exception:
            if lifecycle_run is not None:
                self._lifecycle.update_status(
                    user_id=user_id, run_id=lifecycle_run["id"], status="failed",
                    error_code="opencode_result_persistence_failed",
                )
                self._lifecycle.append_event(
                    user_id=user_id, run_id=lifecycle_run["id"], sequence=2,
                    event_type="task.failed", payload={"code": "opencode_result_persistence_failed"},
                )
            self._broker.release_attempt(task_id, engine_run_id, "opencode")
            raise

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
