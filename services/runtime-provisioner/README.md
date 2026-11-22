# SULY isolated engine Runtime Provisioner

Private control-plane component. It owns Docker access and must run on a dedicated worker host/VM with a dedicated Docker daemon. Never mount the Docker socket into the public API, web app, or task containers.

## Engine runtime profiles

- **OpenCode**: one task-attempt container from OPENCODE_RUNTIME_IMAGE, digest-pinned, exposed internally through its own lease-bound gateway. Its coding workflow, approvals and review/apply lifecycle remain independent.
- **Hermes Agent**: one task-attempt container from HERMES_RUNTIME_IMAGE, digest-pinned from the original NousResearch/hermes-agent source at commit 2de9f51b8008a7d49a49221c184f2f11cbfc4af1. Acquire requires the exact profile suly-hermes-task-v1. Hermes API server binds inside its container on port 8642, authenticated with a per-runtime lease token.
- Both engines have separate containers, internal Docker networks, workspace directories, process trees, runtime credentials, and expiration/teardown. Runtime IDs and token hashes are persisted in SQLite; raw runtime tokens are returned only during acquire/recover and never stored as plaintext.
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

Terminate TLS at a trusted reverse proxy/load balancer. The public SULY API connects to the private provisioner endpoint over TLS. Docker only publishes engine ports on 127.0.0.1. If the provisioner itself runs in a container while using the host Docker socket, it must use host networking (or an equivalently verified host-loopback route); otherwise 127.0.0.1 inside the provisioner container will not reach the Docker host's loopback-published ports. Prefer running this control plane directly on its dedicated worker host.

## Mandatory production controls

1. Use a dedicated VM and restrict Docker socket access to this service. Docker socket access is effectively host-root.
2. Keep task networks internal. Before permitting any outbound traffic, implement and independently verify a task-aware default-deny egress gateway that pins DNS answers at connection time, blocks private/loopback/link-local/metadata destinations, and revalidates redirects and subresources; then restrict the host firewall so tasks can reach only that gateway. Independently block task-bridge access to host services and control-plane/metadata ranges: Docker internal networking alone is not proof of host isolation.
3. Configure TLS, request rate limits, body limits and DDoS protection at ingress.
4. Persist and encrypt SQLite/workspace volumes; do not run multiple replicas with independent local SQLite stores. Multi-host deployments require a shared transactional lease store and distributed watchdog.
5. Results are bounded UTF-8 snapshots. OpenCode applies only a reviewable changeset; Hermes must return a bounded task result that is validated against its task/run lease before SULY accepts it. Neither engine writes directly to Supabase.
6. The gateway uses HTTP only on loopback between the trusted provisioner and runtime. Public access must always be HTTPS.
7. Archive helpers may only create archives when exporting results. Never extract archives produced from task output without validating every member name, size, and type.

## Runtime storage permissions

The provisioner refuses to open its SQLite lease database when the configured path is relative, its parent directory is not owned by the provisioner UID with mode `0700`, or an existing database is not a regular singly-linked file owned by that UID with mode `0600`. The workspace root is subject to the same private-directory ownership and mode check. This is intentionally fail-closed: for an existing persistent volume, an operator must inspect ownership and permissions and correct them explicitly before starting the service. No automatic recursive chmod/chown is performed on mounted data. The provisioner image pins its official Python base by immutable digest, and its `.dockerignore` allowlists only the Dockerfile, requirements, and Python application sources.

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

Provisioner tests use fake Docker clients and API validation. They do not establish that production TLS ingress, host firewall, real Docker daemon, a live Hermes model/provider, or a complete AI task have been validated.
