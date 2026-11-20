"""Docker lifecycle primitives for one isolated OpenCode task attempt.

This module is deliberately not imported by the public API. Run it only in the
separate provisioner service, with a dedicated Docker daemon and host firewall.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

import docker
from docker.errors import APIError, NotFound

_ENGINE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_PATH_PART = re.compile(r"^[A-Za-z0-9._/-]{1,240}$")
_LABEL_PREFIX = "io.suly.runtime"


class RuntimeErrorSafe(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeLimits:
    memory_bytes: int = 2 * 1024**3
    nano_cpus: int = 2_000_000_000
    pids_limit: int = 256
    tmpfs_bytes: int = 256 * 1024**2
    workspace_bytes: int = 64 * 1024**2
    lifetime_seconds: int = 1800

    def validate(self) -> None:
        if not 256 * 1024**2 <= self.memory_bytes <= 8 * 1024**3:
            raise ValueError("runtime_memory_limit_invalid")
        if not 250_000_000 <= self.nano_cpus <= 8_000_000_000:
            raise ValueError("runtime_cpu_limit_invalid")
        if not 32 <= self.pids_limit <= 1024:
            raise ValueError("runtime_pids_limit_invalid")
        if not 32 * 1024**2 <= self.tmpfs_bytes <= 1024**3:
            raise ValueError("runtime_tmpfs_limit_invalid")
        if not 1 <= self.lifetime_seconds <= 3600:
            raise ValueError("runtime_lifetime_invalid")


def _canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("runtime_identity_invalid") from exc
    if str(parsed) != value:
        raise ValueError("runtime_identity_invalid")
    return value


def _safe_workspace(files: list[dict[str, Any]], root: Path, max_bytes: int) -> str:
    if not isinstance(files, list) or len(files) > 200:
        raise ValueError("runtime_workspace_file_count_invalid")
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) - {"path", "content", "sha256"}:
            raise ValueError("runtime_workspace_file_invalid")
        rel = item.get("path")
        content = item.get("content")
        if not isinstance(rel, str) or not _PATH_PART.fullmatch(rel) or "\\" in rel:
            raise ValueError("runtime_workspace_path_invalid")
        pure = PurePosixPath(rel)
        if pure.is_absolute() or any(p in {"", ".", ".."} for p in pure.parts):
            raise ValueError("runtime_workspace_path_invalid")
        if pure.parts[0].lower() in {".git", "node_modules", ".env", "secrets"} or any(p.lower().startswith(".env") for p in pure.parts):
            raise ValueError("runtime_workspace_path_reserved")
        if not isinstance(content, str):
            raise ValueError("runtime_workspace_content_invalid")
        encoded = content.encode("utf-8")
        total += len(encoded)
        if len(encoded) > 256 * 1024 or total > max_bytes:
            raise ValueError("runtime_workspace_size_limit")
        expected = item.get("sha256")
        if expected is not None and expected != hashlib.sha256(encoded).hexdigest():
            raise ValueError("runtime_workspace_digest_mismatch")
        target = root.joinpath(*pure.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        # O_EXCL prevents overwriting a path created earlier in this snapshot.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
    return hashlib.sha256(str(total).encode() + b":" + str(len(files)).encode()).hexdigest()


class DockerTaskRuntimeManager:
    """Creates a fresh network, container, and workspace for each task attempt.

    Networks are internal (no container egress) unless egress is explicitly
    allowed; see the provisioner README for the mandatory host firewall controls.
    """

    def __init__(self, *, image: str, workspace_root: str, limits: RuntimeLimits | None = None, client=None, egress_allowed: bool | None = None):
        if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("runtime_image_must_be_digest_pinned")
        self.image = image
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.limits = limits or RuntimeLimits()
        self.limits.validate()
        self.client = client or docker.from_env()
        # Fail closed: task containers get no outbound network access unless an
        # operator explicitly opts in (RUNTIME_ALLOW_EGRESS=true) and enforces the
        # host firewall egress allowlist documented in the provisioner README.
        if egress_allowed is None:
            egress_allowed = os.environ.get("RUNTIME_ALLOW_EGRESS", "false").strip().lower() in {"1", "true", "yes"}
        self.egress_allowed = bool(egress_allowed)

    def create(self, *, task_id: str, engine_run_id: str, engine_id: str, files: list[dict[str, Any]]) -> dict[str, Any]:
        task_id = _canonical_uuid(task_id)
        run_id = _canonical_uuid(engine_run_id)
        if not isinstance(engine_id, str) or not _ENGINE.fullmatch(engine_id) or engine_id != "opencode":
            raise ValueError("runtime_engine_not_allowed")
        runtime_id = str(uuid4())
        token = secrets.token_urlsafe(48)
        workspace = Path(tempfile.mkdtemp(prefix=f"{runtime_id}-", dir=self.root))
        os.chmod(workspace, 0o700)
        network = container = None
        labels = {
            f"{_LABEL_PREFIX}.id": runtime_id,
            f"{_LABEL_PREFIX}.task": task_id,
            f"{_LABEL_PREFIX}.run": run_id,
            f"{_LABEL_PREFIX}.engine": engine_id,
            f"{_LABEL_PREFIX}.managed": "true",
            f"{_LABEL_PREFIX}.workspace": str(workspace),
            f"{_LABEL_PREFIX}.expires": str(int(time.time() + self.limits.lifetime_seconds)),
        }
        try:
            _safe_workspace(files, workspace, self.limits.workspace_bytes)
            network = self.client.networks.create(
                name=f"suly-{runtime_id}", driver="bridge",
                # Fail closed: an internal network blocks container egress unless
                # explicitly allowed together with the host firewall allowlist.
                internal=not self.egress_allowed,
                check_duplicate=True, labels=labels,
            )
            container = self.client.containers.run(
                self.image,
                detach=True,
                name=f"suly-{runtime_id}",
                network=network.name,
                labels=labels,
                environment={"OPENCODE_SERVER_PASSWORD": token, "OPENCODE_SERVER_USERNAME": "opencode"},
                volumes={str(workspace): {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                ports={"4096/tcp": ("127.0.0.1", None)},
                mem_limit=self.limits.memory_bytes,
                memswap_limit=self.limits.memory_bytes,
                nano_cpus=self.limits.nano_cpus,
                pids_limit=self.limits.pids_limit,
                read_only=True,
                tmpfs={
                    "/tmp": f"rw,noexec,nosuid,size={self.limits.tmpfs_bytes}",
                    "/var/tmp": f"rw,noexec,nosuid,size={self.limits.tmpfs_bytes}",
                    "/var/lib/opencode/config": "rw,nosuid,size=32m,uid=10001,gid=10001",
                    "/var/lib/opencode/data": "rw,nosuid,size=128m,uid=10001,gid=10001",
                    "/home/opencode/.cache": "rw,nosuid,size=128m,uid=10001,gid=10001",
                },
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                privileged=False,
                init=True,
                restart_policy={"Name": "no"},
                tty=False,
                stdin_open=False,
            )
            container.reload()
            port = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get("4096/tcp") or []
            if not port:
                raise RuntimeErrorSafe("runtime_port_not_allocated")
            # Host port is loopback-only. A separately configured TLS gateway must
            # proxy runtime_id -> 127.0.0.1:port; never publish this port publicly.
            binding = port[0]
            if binding.get("HostIp") not in {"127.0.0.1", "::1"}:
                raise RuntimeErrorSafe("runtime_port_binding_not_loopback")
            return {
                "runtime_id": runtime_id, "task_id": task_id, "engine_run_id": run_id,
                "engine_id": engine_id, "container_id": container.id,
                "network_id": network.id, "workspace_path": str(workspace),
                "host_port": int(binding["HostPort"]), "access_token": token,
                "expires_at": time.time() + self.limits.lifetime_seconds,
            }
        except Exception:
            if container is not None:
                try: container.remove(force=True, v=True)
                except Exception: pass
            if network is not None:
                try: network.remove()
                except Exception: pass
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def cleanup_expired(self, *, now: int | None = None) -> int:
        """Reap only SULY-labelled containers whose signed ownership metadata is complete."""
        current = int(time.time()) if now is None else now
        removed = 0
        for container in self.client.containers.list(all=True, filters={"label": f"{_LABEL_PREFIX}.managed=true"}):
            labels = container.labels or {}
            try:
                expiry = int(labels.get(f"{_LABEL_PREFIX}.expires", "0"))
                runtime_id = labels[f"{_LABEL_PREFIX}.id"]
                task_id = labels[f"{_LABEL_PREFIX}.task"]
                run_id = labels[f"{_LABEL_PREFIX}.run"]
            except (KeyError, TypeError, ValueError):
                continue
            if expiry <= current:
                if self.destroy(runtime_id=runtime_id, task_id=task_id, engine_run_id=run_id):
                    removed += 1
        return removed

    def destroy(self, *, runtime_id: str, task_id: str, engine_run_id: str) -> bool:
        runtime_id, task_id, engine_run_id = map(_canonical_uuid, (runtime_id, task_id, engine_run_id))
        try:
            container = self.client.containers.get(f"suly-{runtime_id}")
        except NotFound:
            return False
        labels = container.labels or {}
        expected = {
            f"{_LABEL_PREFIX}.id": runtime_id,
            f"{_LABEL_PREFIX}.task": task_id,
            f"{_LABEL_PREFIX}.run": engine_run_id,
            f"{_LABEL_PREFIX}.managed": "true",
        }
        if any(labels.get(key) != value for key, value in expected.items()):
            raise RuntimeErrorSafe("runtime_ownership_mismatch")
        network_name = f"suly-{runtime_id}"
        workspace = labels.get(f"{_LABEL_PREFIX}.workspace")
        container.remove(force=True, v=True)
        try:
            self.client.networks.get(network_name).remove()
        except NotFound:
            pass
        if workspace:
            resolved = Path(workspace).resolve()
            if resolved.parent != self.root:
                raise RuntimeErrorSafe("runtime_workspace_ownership_mismatch")
            shutil.rmtree(resolved, ignore_errors=True)
        return True
