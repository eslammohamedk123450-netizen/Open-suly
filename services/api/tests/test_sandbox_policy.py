from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.services.sandbox_policy import DockerSandboxCommandBuilder, SandboxLimits


IMAGE = "ghcr.io/suly/agent@sha256:" + "a" * 64


def builder(root: Path, **kwargs):
    return DockerSandboxCommandBuilder(
        workspace_root=root,
        image_ref=IMAGE,
        **kwargs,
    )


def test_sandbox_command_has_hardened_defaults_and_one_workspace_mount(tmp_path):
    root = tmp_path / "workspaces"
    workspace = root / str(uuid4())
    workspace.mkdir(parents=True)
    root.chmod(0o700)
    workspace.chmod(0o700)
    argv = builder(root).build(str(uuid4()), workspace, ["aider", "--help"])
    assert argv[0:3] == ("docker", "run", "--rm")
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in argv
    assert "no-new-privileges:true" in argv
    assert "--pids-limit" in argv
    assert "--memory" in argv
    assert "--cpus" in argv
    assert "--user" in argv
    mounts = [value for value in argv if value.startswith("type=bind,")]
    assert mounts == [f"type=bind,src={workspace.resolve()},dst=/workspace,rw"]
    assert "/var/run/docker.sock" not in argv


@pytest.mark.parametrize("image", [
    "ghcr.io/suly/agent:latest",
    "ghcr.io/suly/agent:v1",
    "ghcr.io/suly/agent@sha256:bad",
])
def test_sandbox_rejects_mutable_or_invalid_image_refs(tmp_path, image):
    root = tmp_path / "workspaces"
    root.mkdir()
    root.chmod(0o700)
    with pytest.raises(ValueError, match="sha256"):
        DockerSandboxCommandBuilder(workspace_root=root, image_ref=image)


def test_sandbox_rejects_workspace_outside_root(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    root.chmod(0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="outside_root"):
        builder(root).build(str(uuid4()), outside, ["aider"])


def test_sandbox_rejects_invalid_task_and_command(tmp_path):
    root = tmp_path / "workspaces"
    workspace = root / str(uuid4())
    workspace.mkdir(parents=True)
    root.chmod(0o700)
    workspace.chmod(0o700)
    sandbox = builder(root)
    with pytest.raises(ValueError, match="task_id"):
        sandbox.build("not-a-uuid", workspace, ["aider"])
    with pytest.raises(ValueError, match="command_required"):
        sandbox.build(str(uuid4()), workspace, [])


def test_sandbox_rejects_symlinked_workspace(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    root.chmod(0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        builder(root).build(str(uuid4()), link, ["aider"])


@pytest.mark.parametrize("limits", [
    SandboxLimits(cpu_count=0),
    SandboxLimits(memory_mb=64),
    SandboxLimits(pids_limit=1),
    SandboxLimits(timeout_seconds=0),
    SandboxLimits(container_uid=True),
    SandboxLimits(cpu_count="1"),
    SandboxLimits(memory_mb="2048"),
    SandboxLimits(timeout_seconds="30"),
])
def test_sandbox_rejects_unsafe_resource_limits(tmp_path, limits):
    root = tmp_path / "workspaces"
    root.mkdir()
    root.chmod(0o700)
    with pytest.raises(ValueError):
        builder(root, limits=limits)


def test_sandbox_rejects_workspace_permissions_visible_to_other_users(tmp_path):
    root = tmp_path / "workspaces"
    workspace = root / str(uuid4())
    workspace.mkdir(parents=True)
    root.chmod(0o700)
    workspace.chmod(0o755)
    with pytest.raises(ValueError, match="permissions_too_open"):
        builder(root).build(str(uuid4()), workspace, ["aider"])


def test_sandbox_rejects_root_container_identity(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    root.chmod(0o700)
    with pytest.raises(ValueError, match="invalid_sandbox_user"):
        builder(root, limits=SandboxLimits(container_uid=0, container_gid=0))
