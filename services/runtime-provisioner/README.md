# SULY isolated engine Runtime Provisioner

Private control-plane component. It owns Docker access and must run on a dedicated worker host/VM with a dedicated Docker daemon. Never mount the Docker socket into the public API, web app, or task containers.

## Engine runtime profiles

- **OpenCode**: one task-attempt container from OPENCODE_RUNTIME_IMAGE, digest-pinned. It is intended to be exposed through a lease-bound gateway, but the current `inhibit_ipv4` task bridge has no host port binding in the live CI Docker check; acquire therefore fails closed with `runtime_gateway_unavailable` until a separate control-network gateway is implemented and verified. Its coding workflow, approvals and review/apply lifecycle remain independent.
- **Hermes Agent**: one task-attempt container from HERMES_RUNTIME_IMAGE, digest-pinned from the original NousResearch/hermes-agent source at commit 2de9f51b8008a7d49a49221c184f2f11cbfc4af1. Acquire requires the exact profile suly-hermes-task-v1. Hermes API server binds inside its container on port 8642, authenticated with a per-runtime lease token.
- Both engines have separate containers, internal Docker networks, workspace directories, process trees, runtime credentials, and expiration/teardown. SQLite enforces at most one runtime record per `(task_id, engine_run_id)`; duplicate requests return 409, and legacy duplicate rows fail startup closed. Runtime IDs and token hashes are persisted in SQLite; raw runtime tokens are returned only during acquire/recover and never stored as plaintext.
- A successful acquire is not an assertion that the runtime is production safe. The profile identifier is an enforced code path in this provisioner, but actual network, container and host isolation still require deployment verification.

## Hermes restrictive defaults

The Hermes runtime profile writes a task-local /opt/data/config.yaml and disables all upstream platform toolsets (platform_toolsets.api_server: []), terminal/browser/computer-use/file/web/MCP/delegate toolsets, memory, user-profile memory, environment probing, and upstream orchestration/subagent spawning. The upstream API route proxy allows only the SULY-required Runs API, its event/stop/steer/one-time-approval controls, health/capabilities/models, and read-only skills/toolsets metadata. It deliberately does not proxy native session APIs or generic /api/* routes.

This is deliberately restrictive, not a claim that Hermes' complete capability set is enabled. Skills and tools remain read-only metadata at present; skill execution, memory write/read, MCP credentials, terminal/browser access, and child-task delegation must be activated only after SULY owns their approvals, tenant scoping, budget ledger and safe execution path.

## Interfaces

- POST /v1/runtimes: SULY-authenticated runtime creation from a bounded workspace snapshot; returns an exact task/run/engine/profile lease.
- POST /v1/runtimes/{runtime_id}/recover: recover the matching live lease after an API/worker restart.
- DELETE /v1/runtimes/{runtime_id}: SULY-authenticated release with exact task/run ownership.
- /v1/runtime-gateway/{runtime_id}/...: task-token-authenticated, engine-specific allowlisted API proxy.
- Hermes routes: Runs API admission/status/events/stop/steer/approval plus read-only skills/toolsets catalog.
- OpenCode routes: existing session/permission/event APIs and bounded execution/results.
- GET /v1/runtimes/{runtime_id}/results: bounded UTF-8 workspace file snapshot for OpenCode results; Hermes outputs remain in SULY task result flow, not via host path sharing.
- POST /internal/cleanup: SULY-authenticated expiry cleanup.

## Configuration

- SULY_PROVISIONER_TOKEN: high-entropy service credential (at least 32 characters).
- RUNTIME_GATEWAY_ORIGIN: public HTTPS origin of this service.
- OPENCODE_RUNTIME_IMAGE: immutable repository@sha256:<64 hex> image built from engines/opencode/Dockerfile.
- HERMES_RUNTIME_IMAGE: immutable repository@sha256:<64 hex> image built from engines/hermes/upstream at its pinned submodule revision. Preserve its upstream MIT license.
- RUNTIME_DB_PATH: persistent volume path (default /var/lib/suly-runtime/runtimes.sqlite3). The database parent must be an absolute, service-owned `0700` directory; an existing database must be a regular, singly-linked, service-owned `0600` file. Symlinks and permissive volume modes are rejected at access time. The image creates the default runtime directories as `0700`; existing mounted volumes must be corrected by the operator before startup.
- RUNTIME_WORKSPACE_ROOT: persistent host work-root for ephemeral runtime directories.
- RUNTIME_ALLOW_EGRESS: must remain unset or a recognized false value (false, 0, no, off). Any truthy or unrecognized value causes provisioner startup to fail. Task networks are always Docker internal; direct egress is deliberately unavailable because no task-aware egress proxy is implemented or verified. Do not enable this setting as a workaround for provider connectivity.

Terminate TLS at a trusted reverse proxy/load balancer. The public SULY API connects to the private provisioner endpoint over TLS. Task engine ports must never be published directly. The current `inhibit_ipv4` task bridge has no host port binding in the live CI Docker check, so the provisioner returns 503 `runtime_gateway_unavailable` and removes the container/network rather than weakening task isolation. A separate control-network gateway/sidecar is required before runtime acquire can work. If the provisioner itself runs in a container while using the host Docker socket, it must use host networking (or an equivalently verified host-loopback route); otherwise 127.0.0.1 inside the provisioner container will not reach the Docker host's loopback-published ports. Prefer running this control plane directly on its dedicated worker host.

## Mandatory production controls

1. Use a dedicated VM and restrict Docker socket access to this service. Docker socket access is effectively host-root.
2. Require Docker Engine 28.0.0 or newer and create every task bridge with `internal=true`, IPv6 disabled, and `com.docker.network.bridge.inhibit_ipv4=true`; also disable bridge ICC and IP masquerading. A normal internal bridge receives a host-side IPv4 address and can expose host services bound to that bridge. `inhibit_ipv4` removes the host-side bridge address, but the 2026-11-22 live CI run showed that the task container receives no host port binding on this network. The runtime manager now fails closed with `runtime_gateway_unavailable` and cleans up; do not weaken the task bridge or publish engine ports to restore connectivity. Implement a separate control-network gateway/sidecar, unreachable from the task network except through its restricted task-side interface, and prove loopback-only host access before enabling acquire. The live-Docker probe verifies no host bridge IPv4, no default route, and blocked host-service, metadata, and external-IP access; it does not verify a runtime gateway. This probe does not replace production host-firewall verification. Before permitting any outbound traffic, implement and independently verify a task-aware default-deny egress gateway that pins DNS answers at connection time, blocks private/loopback/link-local/metadata destinations, and revalidates redirects and subresources; then restrict the host firewall so tasks can reach only that gateway.
3. Configure TLS, request rate limits, body limits and DDoS protection at ingress.
4. Persist and encrypt SQLite/workspace volumes; do not run multiple replicas with independent local SQLite stores. Multi-host deployments require a shared transactional lease store and distributed watchdog.
5. Results are bounded UTF-8 snapshots. OpenCode applies only a reviewable changeset; Hermes must return a bounded task result that is validated against its task/run lease before SULY accepts it. Neither engine writes directly to Supabase.
6. The gateway uses HTTP only on loopback between the trusted provisioner and runtime. Public access must always be HTTPS.
7. Archive helpers may only create archives when exporting results. Never extract archives produced from task output without validating every member name, size, and type.

## Runtime storage permissions

The provisioner refuses to open its SQLite lease database when the configured path is relative, its parent directory is not owned by the provisioner UID with mode `0700`, or an existing database is not a regular singly-linked file owned by that UID with mode `0600`. It also creates a unique `(task_id, engine_run_id)` index; pre-existing duplicate attempts prevent startup until an operator reconciles the records and their Docker resources. The workspace root is subject to the same private-directory ownership and mode check. This is intentionally fail-closed: for an existing persistent volume, an operator must inspect ownership and permissions and correct them explicitly before starting the service. No automatic recursive chmod/chown is performed on mounted data. The provisioner image pins its official Python base by immutable digest, and its `.dockerignore` allowlists only the Dockerfile, requirements, and Python application sources.

## Run the provisioner

```sh
pip install -r requirements.txt
export SULY_PROVISIONER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export RUNTIME_GATEWAY_ORIGIN="https://runtime-gateway.example.com"
export OPENCODE_RUNTIME_IMAGE="registry.example/opencode@sha256:<digest>"
export HERMES_RUNTIME_IMAGE="registry.example/hermes@sha256:<digest>"
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Build the OpenCode image from repository root with engines/opencode/Dockerfile. Build Hermes from the pinned upstream submodule's original Dockerfile:

```sh
git submodule update --init engines/hermes/upstream
docker build -t suly-hermes-agent:local engines/hermes/upstream
```

Never publish the provisioner management port or any task container port directly. Treat Docker socket access as host-root-equivalent.

## Verification

```sh
pip install pytest httpx
PYTHONPATH=. pytest -q tests
```

The default unit/API suite uses fake Docker clients. Runtime Provisioner CI additionally runs the opt-in `test_docker_network_isolation_live.py` against a real Docker Engine 28+ using only a digest-pinned, unprivileged Python probe container (not a SULY engine, worker, or provider). It verifies the isolated bridge has no host IPv4 address, no task default route or published host port, and blocked host-service, metadata-IP, and external-IP access. It does not verify a control-network sidecar gateway; that remains a blocker, and acquire fails closed until it is implemented. This CI probe does not establish production TLS ingress, host firewall policy outside the tested bridge, host-kernel hardening, crash-time process-tree cleanup, a live Hermes model/provider, or a complete AI task.
