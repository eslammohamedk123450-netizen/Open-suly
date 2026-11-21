"""Owner-scoped orchestration from SULY project snapshot to OpenCode results.

This service deliberately returns a reviewable diff payload; it never overwrites
canonical project files automatically.
"""
from __future__ import annotations

from typing import Any
from threading import Event, Thread
import logging
from difflib import unified_diff
import hashlib

from app.services.opencode_session_store import OpenCodeSessionStore
from app.services.project_workspace_store import ProjectWorkspaceStore, contains_secret_material
from app.services.runtime_broker_contract import TaskScopedRuntimeBroker
from app.services.opencode_lifecycle_store import OpenCodeLifecycleStore
from app.services.opencode_event_consumer import OpenCodeEventConsumer


logger = logging.getLogger("suly.opencode.executor")


class OpenCodeTaskExecutor:
    def __init__(
        self,
        *,
        workspace_store: ProjectWorkspaceStore,
        session_store: OpenCodeSessionStore,
        runtime_broker: TaskScopedRuntimeBroker,
        lifecycle_store: OpenCodeLifecycleStore | None = None,
        event_consumer: OpenCodeEventConsumer | None = None,
    ) -> None:
        self._workspace = workspace_store
        self._sessions = session_store
        self._broker = runtime_broker
        self._lifecycle = lifecycle_store
        self._event_consumer = event_consumer or (
            OpenCodeEventConsumer(store=lifecycle_store) if lifecycle_store is not None else None
        )

    def execute(
        self,
        *,
        user_id: str,
        project_id: str,
        task_id: str,
        engine_run_id: str,
        prompt: str,
        title: str = "SULY coding task",
        timeout_seconds: int = 900,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 1800:
            raise ValueError("opencode_timeout_invalid")
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
        session_holder: dict[str, Any] = {}
        event_stop = Event()
        event_thread: Thread | None = None
        cancel_watch_stop = Event()
        cancel_release_done = Event()
        cancel_watch_thread: Thread | None = None

        def watch_cancellation() -> None:
            # فقدان lease يلغي runtime attempt بدل ترك prompt يعمل خارج ملكية المهمة.
            if cancel_event is None:
                return
            while not cancel_watch_stop.wait(0.1):
                if cancel_event.is_set():
                    try:
                        released = self._broker.release_attempt(task_id, engine_run_id, "opencode")
                        if released:
                            cancel_release_done.set()
                        else:
                            logger.warning("OpenCode cancellation cleanup was not confirmed for attempt %s", engine_run_id)
                    except Exception:
                        logger.warning("OpenCode cancellation cleanup failed for attempt %s", engine_run_id)
                    return

        def stop_cancel_watch() -> None:
            cancel_watch_stop.set()
            if cancel_watch_thread is not None:
                cancel_watch_thread.join(timeout=2.0)

        def persist_runtime_lease(lease) -> None:
            if lifecycle_run is None:
                return
            persisted = self._lifecycle.set_runtime(
                user_id=user_id,
                run_id=lifecycle_run["id"],
                runtime_id=lease.runtime_id,
                session_id=None,
                status="provisioning",
            )
            if not persisted:
                raise RuntimeError("opencode_runtime_persistence_failed")
            nonlocal cancel_watch_thread
            if cancel_event is not None and cancel_watch_thread is None:
                cancel_watch_thread = Thread(
                    target=watch_cancellation,
                    name=f"suly-opencode-cancel-{engine_run_id}",
                    daemon=True,
                )
                cancel_watch_thread.start()

        def persist_upstream_session(lease, session_id: str) -> None:
            nonlocal event_thread
            if lifecycle_run is not None:
                persisted = self._lifecycle.set_runtime(
                    user_id=user_id,
                    run_id=lifecycle_run["id"],
                    runtime_id=lease.runtime_id,
                    session_id=session_id,
                    status="running",
                )
                if not persisted:
                    raise RuntimeError("opencode_session_persistence_failed")
            session_holder["session"] = self._sessions.register(
                user_id=user_id,
                project_id=project_id,
                upstream_session_id=session_id,
                title=title,
                task_id=task_id,
                engine_run_id=engine_run_id,
                workspace_revision=snapshot["revision"],
            )
            if lifecycle_run is not None and self._event_consumer is not None:
                def consume_events() -> None:
                    try:
                        self._event_consumer.consume(
                            user_id=user_id,
                            run_id=lifecycle_run["id"],
                            session_id=session_id,
                            base_url=lease.base_url,
                            gateway_path=lease.gateway_path,
                            runtime_token=lease.access_token,
                            sequence_start=10,
                            max_events=500,
                            max_seconds=1800,
                            stop_event=event_stop,
                        )
                    except Exception:
                        logger.warning(
                            "OpenCode event stream stopped for run %s",
                            lifecycle_run["id"],
                        )
                event_thread = Thread(
                    target=consume_events,
                    name=f"suly-opencode-events-{lifecycle_run['id']}",
                    daemon=True,
                )
                event_thread.start()

        try:
            result = self._broker.run_task(
                task_id,
                engine_run_id,
                "opencode",
                files=snapshot["files"],
                prompt=prompt,
                title=title,
                timeout_seconds=timeout_seconds,
                on_lease_acquired=persist_runtime_lease,
                on_session_created=persist_upstream_session,
            )
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("opencode_task_cancelled")
            execution = result.get("execution")
            results = result.get("results")
            if not isinstance(execution, dict) or not isinstance(execution.get("session_id"), str):
                raise RuntimeError("opencode_execution_result_invalid")
            if not isinstance(results, dict) or not isinstance(results.get("changed_files"), list):
                raise RuntimeError("opencode_workspace_result_invalid")
            event_stop.set()
            stop_cancel_watch()
            if event_thread is not None:
                event_thread.join(timeout=3.0)
            if session_holder and session_holder["session"].get("upstream_session_id") != execution["session_id"]:
                raise RuntimeError("opencode_session_identity_mismatch")
            if not session_holder:
                if lifecycle_run is not None and isinstance(execution.get("runtime_id"), str):
                    persisted = self._lifecycle.set_runtime(
                        user_id=user_id, run_id=lifecycle_run["id"],
                        runtime_id=execution["runtime_id"], session_id=execution["session_id"],
                        status="running",
                    )
                    if not persisted:
                        raise RuntimeError("opencode_session_persistence_failed")
                session_holder["session"] = self._sessions.register(
                    user_id=user_id,
                    project_id=project_id,
                    upstream_session_id=execution["session_id"],
                    title=title,
                    task_id=task_id,
                    engine_run_id=engine_run_id,
                    workspace_revision=snapshot["revision"],
                )
        except Exception:
            event_stop.set()
            stop_cancel_watch()
            if event_thread is not None:
                event_thread.join(timeout=1.0)
            if not cancel_release_done.is_set():
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
            session = session_holder["session"]
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
                    if contains_secret_material(new_content):
                        raise ValueError("opencode_result_secret_material_detected")
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
            stop_cancel_watch()
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
