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
    def __init__(self, name, labels, ports=None, container_port="4096/tcp"):
        self.name, self.id, self.labels = name, "container-id", labels
        self.attrs = {"NetworkSettings": {"Ports": {container_port: ports or [{"HostIp": "127.0.0.1", "HostPort": "43123"}]}}}
        self.removed = False
    def reload(self): pass
    def remove(self, **kwargs): self.removed = True


class FakeNetworks:
    def __init__(self): self.items = {}; self.kwargs = None
    def create(self, name, **kwargs):
        self.kwargs = kwargs
        value = FakeNetwork(name); self.items[name] = value; return value
    def get(self, name): return self.items[name]


class FakeContainers:
    def __init__(self): self.items = {}; self.kwargs = None
    def run(self, image, **kwargs):
        self.kwargs = kwargs
        container_port = next(iter(kwargs["ports"]))
        value = FakeContainer(kwargs["name"], kwargs["labels"], container_port=container_port)
        self.items[value.name] = value
        return value
    def get(self, name): return self.items[name]
    def list(self, **kwargs): return list(self.items.values())


class FakeDocker:
    def __init__(self):
        self.networks, self.containers = FakeNetworks(), FakeContainers()


def manager(tmp_path, engine_id="opencode"):
    fake = FakeDocker()
    image_name = "hermes" if engine_id == "hermes-agent" else "opencode"
    return DockerTaskRuntimeManager(
        image=f"registry.example/{image_name}@sha256:" + "a" * 64,
        workspace_root=str(tmp_path), engine_id=engine_id, client=fake,
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
            workspace_root=str(tmp_path), client=FakeDocker(),
        )


def test_network_has_no_outbound_egress_by_default(tmp_path):
    mgr, fake = manager(tmp_path)
    mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode", files=[])
    assert fake.networks.kwargs["internal"] is True


def test_network_egress_cannot_be_enabled_by_constructor(tmp_path):
    fake = FakeDocker()
    with pytest.raises(RuntimeErrorSafe, match="egress_proxy_required"):
        DockerTaskRuntimeManager(
            image="registry.example/opencode@sha256:" + "a" * 64,
            workspace_root=str(tmp_path / "egress"), client=fake, egress_allowed=True,
        )
    assert not fake.networks.items
    assert not fake.containers.items


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_network_egress_env_opt_in_is_rejected_before_docker(tmp_path, monkeypatch, value):
    monkeypatch.setenv("RUNTIME_ALLOW_EGRESS", value)
    fake = FakeDocker()
    with pytest.raises(RuntimeErrorSafe, match="egress_proxy_required"):
        DockerTaskRuntimeManager(
            image="registry.example/opencode@sha256:" + "a" * 64,
            workspace_root=str(tmp_path), client=fake,
        )
    assert not fake.networks.items
    assert not fake.containers.items


@pytest.mark.parametrize("value", ["yes-please", "maybe", "enabled"])
def test_network_egress_env_rejects_unknown_values(tmp_path, monkeypatch, value):
    monkeypatch.setenv("RUNTIME_ALLOW_EGRESS", value)
    fake = FakeDocker()
    with pytest.raises(RuntimeErrorSafe, match="egress_config_invalid"):
        DockerTaskRuntimeManager(
            image="registry.example/opencode@sha256:" + "a" * 64,
            workspace_root=str(tmp_path), client=fake,
        )
    assert not fake.networks.items
    assert not fake.containers.items


@pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
def test_network_egress_false_values_keep_internal_network(tmp_path, monkeypatch, value):
    monkeypatch.setenv("RUNTIME_ALLOW_EGRESS", value)
    mgr, fake = manager(tmp_path)
    mgr.create(task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode", files=[])
    assert fake.networks.kwargs["internal"] is True



def test_hermes_runtime_requires_exact_profile_and_uses_separate_locked_down_container(tmp_path):
    mgr, fake = manager(tmp_path, engine_id="hermes-agent")
    task, run = str(uuid4()), str(uuid4())
    with pytest.raises(ValueError, match="runtime_profile_required"):
        mgr.create(task_id=task, engine_run_id=run, engine_id="hermes-agent", files=[])

    result = mgr.create(
        task_id=task,
        engine_run_id=run,
        engine_id="hermes-agent",
        runtime_profile="suly-hermes-task-v1",
        files=[{"path": "src/app.py", "content": "print('hermes')"}],
    )
    options = fake.containers.kwargs
    assert options["command"] == ["gateway", "run"]
    assert options["ports"] == {"8642/tcp": ("127.0.0.1", None)}
    assert options["environment"]["API_SERVER_ENABLED"] == "true"
    assert options["environment"]["API_SERVER_HOST"] == "0.0.0.0"
    assert options["environment"]["API_SERVER_PORT"] == "8642"
    assert options["environment"]["API_SERVER_KEY"] == result["access_token"]
    assert options["environment"]["HERMES_HOME"] == "/opt/data"
    assert options["environment"]["HERMES_UID"] == str(__import__("os").getuid())
    assert options["environment"]["HERMES_GID"] == str(__import__("os").getgid())
    assert options["cap_drop"] == ["ALL"]
    assert options["privileged"] is False
    assert options["read_only"] is True
    assert fake.networks.kwargs["internal"] is True
    assert result["runtime_profile"] == "suly-hermes-task-v1"
    runtime_root = Path(result["workspace_path"])
    assert (runtime_root / "workspace" / "src" / "app.py").read_text() == "print('hermes')"
    profile = (runtime_root / "hermes_home" / "config.yaml").read_text()
    assert "platform_toolsets:\n  api_server: []" in profile
    assert "\\n" not in profile
    assert "memory_enabled: false" in profile
    assert "orchestrator_enabled: false" in profile
    assert Path(options["volumes"][str(runtime_root / "hermes_home")]["bind"]) == Path("/opt/data")


def test_hermes_runtime_rejects_profile_on_opencode(tmp_path):
    mgr, fake = manager(tmp_path)
    with pytest.raises(ValueError, match="runtime_profile_not_applicable"):
        mgr.create(
            task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="opencode",
            runtime_profile="suly-hermes-task-v1", files=[],
        )
    assert not fake.containers.items


def test_hermes_runtime_rejects_unknown_profile_before_docker(tmp_path):
    mgr, fake = manager(tmp_path, engine_id="hermes-agent")
    with pytest.raises(ValueError, match="runtime_profile_required"):
        mgr.create(
            task_id=str(uuid4()), engine_run_id=str(uuid4()), engine_id="hermes-agent",
            runtime_profile="unrestricted", files=[],
        )
    assert not fake.containers.items


@pytest.mark.parametrize("path", [
    ".ssh/id_rsa",
    ".aws/credentials",
    ".npmrc",
    "config/.netrc",
    "service-account.json",
])
def test_hermes_and_opencode_runtime_reject_sensitive_credential_paths(tmp_path, path):
    mgr, fake = manager(tmp_path)
    with pytest.raises(ValueError, match="path_reserved"):
        mgr.create(
            task_id=str(uuid4()), engine_run_id=str(uuid4()),
            engine_id="opencode",
            files=[{"path": path, "content": "credential file"}],
        )
    assert not fake.containers.items


@pytest.mark.parametrize("content", [
    "-----BEGIN RSA PRIVATE KEY-----\\nprivate-data\\n-----END RSA PRIVATE KEY-----",
    "AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP",
    "GITHUB_TOKEN=ghp_" + "a" * 36,
    "OPENAI_API_KEY=sk-" + "b" * 28,
    "api_key = \"" + "c" * 32 + "\"",
    "SUPABASE_KEY=sb_secret_" + "e" * 32,
])
def test_runtime_rejects_secret_material_before_creating_container(tmp_path, content):
    mgr, fake = manager(tmp_path)
    with pytest.raises(ValueError, match="secret_material_detected"):
        mgr.create(
            task_id=str(uuid4()), engine_run_id=str(uuid4()),
            engine_id="opencode",
            files=[{"path": "src/config.py", "content": content}],
        )
    assert not fake.containers.items


def test_runtime_allows_nonsecret_environment_placeholders(tmp_path):
    mgr, fake = manager(tmp_path)
    mgr.create(
        task_id=str(uuid4()), engine_run_id=str(uuid4()),
        engine_id="opencode",
        files=[{"path": "config/example.env", "content": "API_KEY=${API_KEY}\\nPASSWORD=YOUR_PASSWORD"}],
    )
    assert len(fake.containers.items) == 1
