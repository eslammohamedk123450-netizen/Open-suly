from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.docker_runtime import DockerTaskRuntimeManager, RuntimeLimits, RuntimeErrorSafe


class FakeNetwork:
    def __init__(self, name):
        self.name, self.id, self.removed = name, "network-id", False
    def remove(self): self.removed = True


class FakeContainer:
    def __init__(self, name, labels, ports=None):
        self.name, self.id, self.labels = name, "container-id", labels
        self.attrs = {"NetworkSettings": {"Ports": {"4096/tcp": ports or [{"HostIp": "127.0.0.1", "HostPort": "43123"}]}}}
        self.removed = False
    def reload(self): pass
    def remove(self, **kwargs): self.removed = True


class FakeNetworks:
    def __init__(self): self.items = {}
    def create(self, name, **kwargs):
        value = FakeNetwork(name); self.items[name] = value; return value
    def get(self, name): return self.items[name]


class FakeContainers:
    def __init__(self): self.items = {}; self.kwargs = None
    def run(self, image, **kwargs):
        self.kwargs = kwargs
        value = FakeContainer(kwargs["name"], kwargs["labels"])
        self.items[value.name] = value
        return value
    def get(self, name): return self.items[name]
    def list(self, **kwargs): return list(self.items.values())


class FakeDocker:
    def __init__(self):
        self.networks, self.containers = FakeNetworks(), FakeContainers()


def manager(tmp_path):
    fake = FakeDocker()
    return DockerTaskRuntimeManager(
        image="registry.example/opencode@sha256:" + "a" * 64,
        workspace_root=str(tmp_path), client=fake,
    ), fake


def test_create_enforces_container_hardening_and_unique_workspace_network(tmp_path):
    mgr, fake = manager(tmp_path)
    task, run = str(uuid4()), str(uuid4())
    result = mgr.create(task_id=task, engine_run_id=run, engine_id="opencode",
                        files=[{"path": "src/main.py", "content": "print('ok')"}])
    options = fake.containers.kwargs
    assert options["privileged"] is False
    assert options["read_only"] is True
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["mem_limit"] == options["memswap_limit"]
    assert options["pids_limit"] == 256
    assert "/var/lib/opencode/config" in options["tmpfs"]
    assert "/var/lib/opencode/data" in options["tmpfs"]
    assert options["ports"]["4096/tcp"] == ("127.0.0.1", None)
    assert result["host_port"] == 43123
    assert Path(result["workspace_path"], "src/main.py").read_text() == "print('ok')"


def test_create_rejects_workspace_traversal_before_container_creation(tmp_path):
    mgr, fake = manager(tmp_path)
    with pytest.raises(ValueError, match="path_invalid"):
        mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode",
                   files=[{"path": "../escape", "content": "x"}])
    assert not fake.containers.items


def test_create_rejects_secret_files_and_digest_mismatch(tmp_path):
    mgr, fake = manager(tmp_path)
    with pytest.raises(ValueError, match="reserved"):
        mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode",
                   files=[{"path": ".env.production", "content": "secret"}])
    with pytest.raises(ValueError, match="digest_mismatch"):
        mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode",
                   files=[{"path": "a.txt", "content": "hello", "sha256": "0" * 64}])
    assert not fake.containers.items


def test_destroy_checks_exact_task_attempt_ownership(tmp_path):
    mgr, fake = manager(tmp_path)
    task, run = str(uuid4()), str(uuid4())
    result = mgr.create(task_id=task, engine_run_id=run, engine_id="opencode", files=[])
    with pytest.raises(RuntimeErrorSafe, match="ownership_mismatch"):
        mgr.destroy(runtime_id=result["runtime_id"], task_id=str(uuid4()), engine_run_id=run)
    assert not fake.containers.items[f"suly-{result['runtime_id']}"].removed
    assert mgr.destroy(runtime_id=result["runtime_id"], task_id=task, engine_run_id=run)


def test_create_rejects_non_loopback_port_binding_and_cleans_up(tmp_path):
    mgr, fake = manager(tmp_path)
    fake.containers.run = lambda image, **kwargs: FakeContainer(
        kwargs["name"], kwargs["labels"],
        ports=[{"HostIp": "0.0.0.0", "HostPort": "43123"}],
    )
    with pytest.raises(RuntimeErrorSafe, match="loopback"):
        mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode", files=[])



def test_image_must_use_a_full_sha256_digest(tmp_path):
    with pytest.raises(ValueError, match="digest_pinned"):
        DockerTaskRuntimeManager(
            image="registry.example/opencode:latest",
            workspace_root=str(tmp_path),
            client=FakeDocker(),
        )
