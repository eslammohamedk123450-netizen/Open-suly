"""Docker lifecycle primitives for one isolated SULY engine task attempt.

This module runs only inside the trusted runtime provisioner. Each attempt gets
its own internal network, container, workspace, data directory and lease.
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
from typing import Any, Callable
from uuid import UUID, uuid4

import docker
from docker.errors import APIError, NotFound

_ENGINE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_PATH_PART = re.compile(r"^[A-Za-z0-9._/-]{1,240}$")
_LABEL_PREFIX = "io.suly.runtime"
_BLOCKED_PATH_PARTS = {
    ".git", "node_modules", ".env", "secrets", ".ssh", ".aws",
    ".azure", ".gcloud", ".docker", ".kube", ".gnupg",
}
_BLOCKED_FILE_NAMES = {
    ".npmrc", ".pypirc", ".netrc", ".pgpass", "credentials",
    "credentials.json", "id_rsa", "id_ed25519", "id_ecdsa",
    "service-account.json", "dockerconfig.json",
}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"""(?im)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\s*[:=]\s*["']?(?!\$\{|\{\{|YOUR_|CHANGEME|REPLACE_ME|example|placeholder)[A-Za-z0-9_./+=-]{24,}"""
    ),
)


def _contains_secret_material(content: str) -> bool:
    return any(pattern.search(content) for pattern in _SECRET_PATTERNS)


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
        if any(
            part.lower() in _BLOCKED_PATH_PARTS
            or part.lower() in _BLOCKED_FILE_NAMES
            or part.lower().startswith(".env")
            for part in pure.parts
        ):
            raise ValueError("runtime_workspace_path_reserved")
        if not isinstance(content, str):
            raise ValueError("runtime_workspace_content_invalid")
        if _contains_secret_material(content):
            raise ValueError("runtime_workspace_secret_material_detected")
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


def validate_egress_disabled(value: object | None = None) -> None:
    """Reject direct task egress until a task-aware, enforced proxy exists.

    A Docker bridge marked internal=False is not an egress allowlist. The
    provisioner currently has no proxy/firewall attestation, so even an explicit
    operator opt-in must fail closed rather than expose arbitrary outbound access.
    """
    configured = os.environ.get("RUNTIME_ALLOW_EGRESS", "false") if value is None else value
    if type(configured) is bool:
        enabled = configured
    elif isinstance(configured, str):
        normalized = configured.strip().lower()
        if normalized in {"0", "false", "no", "off", ""}:
            return
        if normalized in {"1", "true", "yes", "on"}:
            raise RuntimeErrorSafe("runtime_egress_proxy_required")
        raise RuntimeErrorSafe("runtime_egress_config_invalid")
    else:
        raise RuntimeErrorSafe("runtime_egress_config_invalid")
    if enabled:
        raise RuntimeErrorSafe("runtime_egress_proxy_required")


class DockerTaskRuntimeManager:
    """Creates a fresh internal network, container, and workspace per attempt.

    Task containers have no direct external routing. Direct egress stays blocked
    until a task-aware proxy enforces DNS pinning, destination policy, and redirects.
    """

    def __init__(self, *, image: str, workspace_root: str, engine_id: str = "opencode", limits: RuntimeLimits | None = None, client=None, egress_allowed: bool | None = None):
        if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("runtime_image_must_be_digest_pinned")
        # Validate before touching the workspace or Docker daemon. No direct
        # outbound mode is available until a task-aware egress proxy is enforced.
        validate_egress_disabled(egress_allowed)
        if engine_id not in {"opencode", "hermes-agent"}:
            raise ValueError("runtime_engine_not_allowed")
        self.engine_id = engine_id
        self.image = image
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.limits = limits or RuntimeLimits()
        self.limits.validate()
        self.client = client or docker.from_env()

    def create(
        self,
        *,
        task_id: str,
        engine_run_id: str,
        engine_id: str,
        files: list[dict[str, Any]],
        runtime_profile: str | None = None,
        access_token_factory: Callable[[str, str, str], str] | None = None,
    ) -> dict[str, Any]:
        task_id = _canonical_uuid(task_id)
        run_id = _canonical_uuid(engine_run_id)
        if engine_id not in {"opencode", "hermes-agent"} or engine_id != self.engine_id:
            raise ValueError("runtime_engine_not_allowed")
        if engine_id == "hermes-agent" and runtime_profile != "suly-hermes-task-v1":
            raise ValueError("runtime_profile_required")
        if engine_id == "opencode" and runtime_profile is not None:
            raise ValueError("runtime_profile_not_applicable")
        runtime_id = str(uuid4())
        token = (
            access_token_factory(runtime_id, task_id, run_id)
            if access_token_factory is not None
            else secrets.token_urlsafe(48)
        )
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~+/-]{32,256}", token):
            raise ValueError("runtime_access_token_invalid")
        runtime_root = Path(tempfile.mkdtemp(prefix=f"{runtime_id}-", dir=self.root))
        os.chmod(runtime_root, 0o700)
        workspace = runtime_root / "workspace" if engine_id == "hermes-agent" else runtime_root
        hermes_home = runtime_root / "hermes_home" if engine_id == "hermes-agent" else None
        network = container = None
        try:
            workspace.mkdir(mode=0o700, exist_ok=True)
            if hermes_home is not None:
                hermes_home.mkdir(mode=0o700, exist_ok=True)
                # The upstream API server reads this profile at process start. An
                # explicit empty list is intentional: no terminal/browser/MCP/file
                # toolsets are exposed until a reviewed SULY grant and egress proxy
                # are implemented. Native memory and native delegation are off;
                # SULY owns conversation context and future delegated child tasks.
                hermes_config = (
                    "platform_toolsets:\n"
                    "  api_server: []\n"
                    "agent:\n"
                    "  disabled_toolsets: [terminal, browser, computer_use, file, web, mcp, delegate_task, skills, memory]\n"
                    "  environment_probe: false\n"
                    "terminal:\n"
                    "  cwd: /workspace\n"
                    "  env_passthrough: []\n"
                    "  client_env_passthrough: []\n"
                    "  docker_forward_env: []\n"
                    "  docker_env: {}\n"
                    "memory:\n"
                    "  memory_enabled: false\n"
                    "  user_profile_enabled: false\n"
                    "  write_approval: true\n"
                    "delegation:\n"
                    "  orchestrator_enabled: false\n"
                    "  max_spawn_depth: 1\n"
                    "  max_concurrent_children: 1\n"
                    "  oneshot_max_children: 0\n"
                )
                config_path = hermes_home / "config.yaml"
                fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(hermes_config)
                # Hermes supports runtime UID/GID remapping in its own stage2
                # hook. Match the non-root provisioner identity that owns these
                # fresh bind mounts instead of calling chown on the host (which
                # would require CAP_CHOWN and is not available to the CI/test user).
        except Exception:
            shutil.rmtree(runtime_root, ignore_errors=True)
            raise
        labels = {
            f"{_LABEL_PREFIX}.id": runtime_id,
            f"{_LABEL_PREFIX}.task": task_id,
            f"{_LABEL_PREFIX}.run": run_id,
            f"{_LABEL_PREFIX}.engine": engine_id,
            f"{_LABEL_PREFIX}.managed": "true",
            f"{_LABEL_PREFIX}.workspace": str(runtime_root),
            f"{_LABEL_PREFIX}.expires": str(int(time.time() + self.limits.lifetime_seconds)),
        }
        try:
            _safe_workspace(files, workspace, self.limits.workspace_bytes)
            is_hermes = engine_id == "hermes-agent"
            container_port = "8642/tcp" if is_hermes else "4096/tcp"
            container_environment = (
                {
                    "API_SERVER_ENABLED": "true",
                    "API_SERVER_KEY": token,
                    "API_SERVER_HOST": "0.0.0.0",
                    "API_SERVER_PORT": "8642",
                    "API_SERVER_MODEL_NAME": "hermes-agent",
                    "HERMES_HOME": "/opt/data",
                    "HERMES_UID": str(os.getuid()),
                    "HERMES_GID": str(os.getgid()),
                }
                if is_hermes
                else {"OPENCODE_SERVER_PASSWORD": token, "OPENCODE_SERVER_USERNAME": "opencode"}
            )
            container_volumes = (
                {
                    str(workspace): {"bind": "/workspace", "mode": "rw"},
                    str(hermes_home): {"bind": "/opt/data", "mode": "rw"},
                }
                if is_hermes
                else {str(workspace): {"bind": "/workspace", "mode": "rw"}}
            )
            container_tmpfs = {
                "/tmp": f"rw,noexec,nosuid,size={self.limits.tmpfs_bytes}",
                "/var/tmp": f"rw,noexec,nosuid,size={self.limits.tmpfs_bytes}",
            }
            if is_hermes:
                container_tmpfs["/opt/data/.cache"] = (
                    f"rw,nosuid,nodev,size=128m,uid={os.getuid()},gid={os.getgid()}"
                )
            else:
                container_tmpfs.update({
                    "/var/lib/opencode/config": "rw,nosuid,size=32m,uid=10001,gid=10001",
                    "/var/lib/opencode/data": "rw,nosuid,size=128m,uid=10001,gid=10001",
                    "/home/opencode/.cache": "rw,nosuid,size=128m,uid=10001,gid=10001",
                })
            network = self.client.networks.create(
                name=f"suly-{runtime_id}", driver="bridge",
                # Always internal: no proxy or destination enforcement exists yet.
                internal=True,
                check_duplicate=True, labels=labels,
            )
            container = self.client.containers.run(
                self.image,
                command=["gateway", "run"] if is_hermes else None,
                detach=True,
                name=f"suly-{runtime_id}",
                network=network.name,
                labels=labels,
                environment=container_environment,
                volumes=container_volumes,
                working_dir="/workspace",
                ports={container_port: ("127.0.0.1", None)},
                mem_limit=self.limits.memory_bytes,
                memswap_limit=self.limits.memory_bytes,
                nano_cpus=self.limits.nano_cpus,
                pids_limit=self.limits.pids_limit,
                read_only=True,
                tmpfs=container_tmpfs,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                privileged=False,
                init=True,
                restart_policy={"Name": "no"},
                tty=False,
                stdin_open=False,
            )
            container.reload()
            port = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get(container_port) or []
            if not port:
                raise RuntimeErrorSafe("runtime_port_not_allocated")
            # Host port is loopback-only. A separately configured TLS gateway must
            # proxy runtime_id -> 127.0.0.1:port; never publish this port publicly.
            binding = port[0]
            if binding.get("HostIp") not in {"127.0.0.1", "::1"}:
                raise RuntimeErrorSafe("runtime_port_binding_not_loopback")
            return {
                "runtime_id": runtime_id, "task_id": task_id, "engine_run_id": run_id,
                "engine_id": engine_id, "runtime_profile": runtime_profile,
                "container_id": container.id, "network_id": network.id,
                "workspace_path": str(runtime_root),
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
            shutil.rmtree(runtime_root, ignore_errors=True)
            raise

    def cleanup_expired(self, *, now: int | None = None) -> int:
        """Reap only SULY-labelled containers whose signed ownership metadata is complete."""
        current = int(time.time()) if now is None else now
        removed = 0
        for container in self.client.containers.list(
            all=True,
            filters={"label": [
                f"{_LABEL_PREFIX}.managed=true",
                f"{_LABEL_PREFIX}.engine={self.engine_id}",
            ]},
        ):
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
            f"{_LABEL_PREFIX}.engine": self.engine_id,
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
