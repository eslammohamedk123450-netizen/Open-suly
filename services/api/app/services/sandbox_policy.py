"""Fail-closed Docker sandbox command policy for future engine runtimes.

هذه الوحدة تبني أمر Docker آمنًا مبدئيًا فقط؛ لا تنفذ Docker ولا تنشئ حاويات.
يجب أن تكون مساحة العمل مؤقتة وموثوقة المصدر، والصورة مثبتة بـsha256 digest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from uuid import UUID


_IMAGE_DIGEST = re.compile(r"^[A-Za-z0-9._/:+-]+@sha256:[a-f0-9]{64}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class SandboxLimits:
    """حدود الموارد التي يفرضها Docker على كل تنفيذ منفصل."""

    cpu_count: float = 1.0
    memory_mb: int = 2048
    pids_limit: int = 128
    timeout_seconds: int = 300
    tmpfs_mb: int = 128
    container_uid: int = field(default_factory=os.getuid)
    container_gid: int = field(default_factory=os.getgid)

    def validate(self) -> None:
        if isinstance(self.cpu_count, bool) or not isinstance(self.cpu_count, (int, float)) or not 0.1 <= self.cpu_count <= 8:
            raise ValueError("invalid_sandbox_cpu_limit")
        if isinstance(self.memory_mb, bool) or not isinstance(self.memory_mb, int) or not 128 <= self.memory_mb <= 32768:
            raise ValueError("invalid_sandbox_memory_limit")
        if isinstance(self.pids_limit, bool) or not isinstance(self.pids_limit, int) or not 16 <= self.pids_limit <= 1024:
            raise ValueError("invalid_sandbox_pids_limit")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 3600:
            raise ValueError("invalid_sandbox_timeout")
        if isinstance(self.tmpfs_mb, bool) or not isinstance(self.tmpfs_mb, int) or not 16 <= self.tmpfs_mb <= 2048:
            raise ValueError("invalid_sandbox_tmpfs_limit")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535
            for value in (self.container_uid, self.container_gid)
        ):
            raise ValueError("invalid_sandbox_user")


class DockerSandboxCommandBuilder:
    """Build a non-executing Docker CLI invocation with one workspace mount."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        image_ref: str,
        limits: SandboxLimits | None = None,
    ) -> None:
        if not isinstance(image_ref, str) or not _IMAGE_DIGEST.fullmatch(image_ref):
            raise ValueError("sandbox_image_must_be_pinned_by_sha256")
        self.limits = limits or SandboxLimits()
        self.limits.validate()
        self.workspace_root = Path(workspace_root).resolve(strict=True)
        if not self.workspace_root.is_dir():
            raise ValueError("sandbox_workspace_root_must_be_directory")
        self._validate_private_directory(self.workspace_root)
        if not _SAFE_PATH.fullmatch(str(self.workspace_root)):
            raise ValueError("sandbox_workspace_path_contains_unsupported_characters")
        self.image_ref = image_ref

    def _validate_private_directory(self, path: Path) -> None:
        """تأكد أن مساحة العمل خاصة ومملوكة لهوية المستخدم غير الجذر داخل الحاوية."""
        info = path.stat()
        if info.st_uid != self.limits.container_uid or info.st_gid != self.limits.container_gid:
            raise ValueError("sandbox_workspace_owner_mismatch")
        if info.st_mode & 0o077:
            raise ValueError("sandbox_workspace_permissions_too_open")

    def build(
        self,
        task_id: str,
        workspace_path: str | Path,
        command: tuple[str, ...] | list[str],
        *,
        engine_run_id: str | None = None,
    ) -> tuple[str, ...]:
        """Return argv for one attempt; callers must enforce a wall-clock timeout.

        engine_run_id must be supplied by production provisioners so retries of
        one task cannot collide on a Docker name or accidentally share a runtime.
        The task_id fallback exists only for backwards-compatible policy tests.
        """
        try:
            normalized_task_id = str(UUID(task_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_sandbox_task_id") from exc
        if engine_run_id is None:
            normalized_run_id = normalized_task_id
        else:
            try:
                normalized_run_id = str(UUID(engine_run_id))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_sandbox_engine_run_id") from exc
        if not isinstance(command, (tuple, list)) or not command:
            raise ValueError("sandbox_command_required")
        if any(
            not isinstance(part, str) or not part or "\x00" in part
            for part in command
        ):
            raise ValueError("invalid_sandbox_command")

        raw_workspace = Path(workspace_path)
        # نرفض الروابط الرمزية في المسار حتى لا يتم توجيه mount خارج الجذر.
        cursor = raw_workspace
        while cursor != cursor.parent:
            if cursor.is_symlink():
                raise ValueError("sandbox_workspace_symlink_not_allowed")
            if cursor == self.workspace_root:
                break
            cursor = cursor.parent
        workspace = raw_workspace.resolve(strict=True)
        try:
            workspace.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("sandbox_workspace_outside_root") from exc
        if not workspace.is_dir():
            raise ValueError("sandbox_workspace_must_be_directory")
        self._validate_private_directory(workspace)
        if not _SAFE_PATH.fullmatch(str(workspace)):
            raise ValueError("sandbox_workspace_path_contains_unsupported_characters")

        limits = self.limits
        argv = [
            "docker", "run", "--rm", "--pull=never", "--init",
            "--name", f"suly-run-{normalized_run_id}",
            "--label", f"com.suly.task-id={normalized_task_id}",
            "--label", f"com.suly.engine-run-id={normalized_run_id}",
            "--network", "none",
            "--pid", "private",
            "--ipc", "private",
            "--uts", "private",
            "--restart", "no",
            "--log-driver", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--security-opt", "seccomp=default",
            "--pids-limit", str(limits.pids_limit),
            "--ulimit", "nofile=1024:1024",
            "--ulimit", "core=0",
            "--memory", f"{limits.memory_mb}m",
            "--memory-swap", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_count),
            "--stop-timeout", "5",
            "--user", f"{limits.container_uid}:{limits.container_gid}",
            "--workdir", "/workspace",
            "--env", "HOME=/home/agent",
            "--env", "TMPDIR=/tmp",
            "--tmpfs", f"/tmp:rw,nosuid,nodev,noexec,size={limits.tmpfs_mb}m,uid={limits.container_uid},gid={limits.container_gid},mode=1777",
            "--tmpfs", f"/home/agent:rw,nosuid,nodev,noexec,size={limits.tmpfs_mb}m,uid={limits.container_uid},gid={limits.container_gid},mode=0700",
            "--mount", f"type=bind,src={workspace},dst=/workspace,rw",
            self.image_ref,
            *command,
        ]
        return tuple(argv)
