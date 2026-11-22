"""Opt-in live Docker proof for the task network isolation boundary.

This starts only a disposable Python HTTP probe container. It never starts a
SULY engine, worker, provider, or user task.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

import docker
import pytest

from app.docker_runtime import _create_isolated_task_network


pytestmark = pytest.mark.skipif(
    os.getenv("SULY_DOCKER_NETWORK_ISOLATION_TEST") != "1",
    reason="requires an explicit real-Docker CI opt-in",
)


def _host_ipv4_addresses() -> list[str]:
    """Return host interface IPv4 addresses without loopback."""
    result = subprocess.run(
        ["ip", "-o", "-4", "addr", "show"],
        check=True,
        capture_output=True,
        text=True,
    )
    addresses = set()
    for line in result.stdout.splitlines():
        match = re.search(r"\binet\s+([0-9.]+)/", line)
        if match and not match.group(1).startswith("127."):
            addresses.add(match.group(1))
    return sorted(addresses)


def test_isolated_bridge_blocks_host_and_external_access_but_keeps_loopback_gateway():
    """Prove Docker Engine's isolated internal bridge on the CI host."""
    image = os.getenv("RUNTIME_NETWORK_TEST_IMAGE", "")
    if not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", image):
        pytest.fail("RUNTIME_NETWORK_TEST_IMAGE must be an immutable digest")

    client = docker.from_env()
    container = None
    network = None
    host_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        version = client.version().get("Version", "")
        version_match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if not version_match or tuple(map(int, version_match.groups())) < (28, 0, 0):
            pytest.fail("Docker Engine 28.0.0 or newer is required for isolated gateway mode")

        host_addresses = _host_ipv4_addresses()
        assert host_addresses, "CI host must expose at least one non-loopback IPv4 address"
        host_listener.bind(("0.0.0.0", 0))
        host_listener.listen(16)
        host_service_port = host_listener.getsockname()[1]

        suffix = uuid4().hex[:12]
        network = _create_isolated_task_network(
            client,
            name=f"suly-isolation-probe-{suffix}",
            labels={"io.suly.runtime.integration-test": "true"},
        )
        network.reload()
        assert network.attrs.get("Internal") is True
        assert network.attrs.get("EnableIPv6") is False
        options = network.attrs.get("Options") or {}
        assert options.get("com.docker.network.bridge.gateway_mode_ipv4") == "isolated"
        assert options.get("com.docker.network.bridge.enable_icc") == "false"
        assert options.get("com.docker.network.bridge.enable_ip_masquerade") == "false"

        # A host-side bridge address is the path that makes ordinary internal
        # bridge networks able to reach services listening on 0.0.0.0.
        bridge_name = options.get("com.docker.network.bridge.name") or f"br-{network.id[:12]}"
        bridge_addresses = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", "dev", bridge_name],
            check=True,
            capture_output=True,
            text=True,
        )
        assert not bridge_addresses.stdout.strip(), "isolated bridge unexpectedly has a host IPv4 address"

        container = client.containers.run(
            image,
            command=["python", "-m", "http.server", "8080", "--bind", "0.0.0.0"],
            name=f"suly-isolation-probe-{suffix}",
            detach=True,
            network=network.name,
            ports={"8080/tcp": ("127.0.0.1", None)},
            user="65534:65534",
            read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=8m"},
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit="64m",
            pids_limit=16,
            restart_policy={"Name": "no"},
        )
        container.reload()
        bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get("8080/tcp") or []
        assert len(bindings) == 1
        assert bindings[0].get("HostIp") == "127.0.0.1"
        host_port = int(bindings[0]["HostPort"])

        # Verify the only intended ingress path remains usable from the trusted
        # host-side provisioner: an explicit loopback-only published port.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{host_port}/", timeout=1) as response:
                    assert response.status == 200
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        else:
            pytest.fail("loopback-published runtime gateway did not become reachable")

        probe = r'''
import json
import socket
import sys

host_addresses = json.loads(sys.argv[1])
host_port = int(sys.argv[2])
for address in host_addresses:
    try:
        with socket.create_connection((address, host_port), timeout=1):
            pass
    except OSError:
        continue
    print("host_service_reachable:" + address)
    raise SystemExit(21)
print("host_services_blocked")

routes = open("/proc/net/route", encoding="ascii").read().splitlines()[1:]
if any(line.split()[1] == "00000000" for line in routes if len(line.split()) > 1):
    print("default_route_present")
    raise SystemExit(22)

try:
    with socket.create_connection(("1.1.1.1", 443), timeout=1):
        pass
except OSError:
    print("external_egress_blocked")
else:
    print("external_egress_reachable")
    raise SystemExit(23)
'''
        result = container.exec_run(
            ["python", "-c", probe, json.dumps(host_addresses), str(host_service_port)],
            user="65534:65534",
        )
        output = result.output.decode("utf-8", errors="replace")
        assert result.exit_code == 0, output
        assert "host_services_blocked" in output
        assert "external_egress_blocked" in output
finally:
        if container is not None:
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        if network is not None:
            try:
                network.remove()
            except docker.errors.NotFound:
                pass
        host_listener.close()
        client.close()
