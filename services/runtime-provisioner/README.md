# SULY isolated OpenCode Runtime Provisioner

Private control-plane component. It owns Docker access and must run on a dedicated worker host/VM with a dedicated Docker daemon. Never mount the Docker socket into the public API, web app, or task containers.

## Interfaces

- `POST /v1/runtimes`: SULY-authenticated runtime creation from a bounded workspace snapshot; returns a one-time runtime token and HTTPS gateway URL.
- `DELETE /v1/runtimes/{runtime_id}`: SULY-authenticated release with exact task/run ownership.
- `/v1/runtime-gateway/{runtime_id}/...`: task-token-authenticated allowlisted OpenCode API proxy. Container port remains loopback-only.
- `POST /v1/runtime-gateway/{runtime_id}/execute`: create/reuse a session and submit a bounded prompt to the original OpenCode server.
- `GET /v1/runtimes/{runtime_id}/results`: export bounded UTF-8 workspace files; symlinks, secrets, .git, node_modules and binary files are excluded.
- `POST /internal/cleanup`: SULY-authenticated expiry cleanup.

Runtime ownership, container mapping, token hashes, expiry and the initial workspace hash map are stored in SQLite. Raw per-runtime tokens are returned only on creation and are not stored. The API waits for authenticated `/api/info` readiness before issuing the lease. The SULY provider can pass a bounded file snapshot, submit a prompt, and retrieve changed/deleted file metadata and contents.

## Configuration

- `SULY_PROVISIONER_TOKEN`: high-entropy service credential (at least 32 characters).
- `RUNTIME_GATEWAY_ORIGIN`: public HTTPS origin of this service.
- `OPENCODE_RUNTIME_IMAGE`: immutable `repository@sha256:<64 hex>` image built from `engines/opencode/Dockerfile`.
- `RUNTIME_DB_PATH`: persistent volume path (default `/var/lib/suly-runtime/runtimes.sqlite3`).
- `RUNTIME_WORKSPACE_ROOT`: persistent workspace path.
- `RUNTIME_ALLOW_EGRESS`: must remain unset or a recognized false value (`false`, `0`, `no`, `off`). Any truthy or unrecognized value causes provisioner startup to fail. Task networks are always Docker `internal`; direct egress is deliberately unavailable because no task-aware egress proxy is implemented or verified. Do not enable this setting as a workaround for provider connectivity.

Terminate TLS at a trusted reverse proxy/load balancer. The public SULY API connects to the private provisioner endpoint over TLS. Docker only publishes OpenCode on 127.0.0.1. If the provisioner itself runs in a container while using the host Docker socket, it must use host networking (or an equivalently verified host-loopback route); otherwise 127.0.0.1 inside the provisioner container will not reach the Docker host's loopback-published ports. Prefer running this control plane directly on its dedicated worker host.

## Mandatory production controls

1. Use a dedicated VM and restrict Docker socket access to this service. Docker socket access is effectively host-root.
2. Keep task networks internal. Before permitting any outbound traffic, implement and independently verify a task-aware default-deny egress gateway that pins DNS answers at connection time, blocks private/loopback/link-local/metadata destinations, and revalidates redirects and subresources; then restrict the host firewall so tasks can reach only that gateway. Independently block task-bridge access to host services and control-plane/metadata ranges: Docker internal networking alone is not proof of host isolation. A host firewall note or internal=False network is not proof of destination enforcement.
3. Configure TLS, request rate limits, body limits and DDoS protection at ingress.
4. Persist and encrypt SQLite/workspace volumes; do not run multiple replicas with independent local SQLite stores. Multi-host deployments require a shared transactional lease store and distributed watchdog.
5. Results are a bounded UTF-8 snapshot with changed files and deleted paths compared with the initial content hashes; binary files, symlinks and files over 1 MiB are omitted. The provider exposes `run_task()` to submit and collect the result. SULY must apply results against the recorded workspace revision and show a reviewable diff before changing canonical project files; this provisioner does not write directly to Supabase.
6. The gateway uses HTTP only on loopback between gateway and container. Public access must always be HTTPS.
7. Archive helpers (for example Python's `tarfile`) may only create archives when exporting results. Never extract archives produced from task output without validating every member name, size, and type; a malicious archive can traverse paths or expand without bounds (zip bomb). The workspace is a host bind mount and must be read directly, never through archive extraction.

## Run

```sh
pip install -r requirements.txt
export SULY_PROVISIONER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export RUNTIME_GATEWAY_ORIGIN="https://runtime-gateway.example.com"
export OPENCODE_RUNTIME_IMAGE="registry.example/opencode@sha256:<digest>"
# Recommended: run the provisioner on the dedicated Docker worker host.
# If containerized, host networking is required because task ports are published
# only on the worker host's 127.0.0.1. Add only the Docker socket's numeric group.
docker run --rm --network host \
  --group-add "$(stat -c '%g' /var/run/docker.sock)" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/lib/suly-runtime:/var/lib/suly-runtime \
  --env-file /etc/suly-runtime.env \
  suly-runtime-provisioner:local

# Or run uvicorn directly on the dedicated host:
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

The service must have access to its dedicated Docker daemon. Treat Docker socket access as host-root-equivalent. Build the OpenCode image from repository root with `engines/opencode/Dockerfile`. Put the TLS reverse proxy in front of the loopback-bound provisioner API; do not publish port 8080 or any task container port directly.

## Verification

```sh
pip install pytest httpx
PYTHONPATH=. pytest -q tests
```

Tests use fake Docker clients and API validation tests. They do not establish that production TLS ingress, host firewall, real Docker daemon or a full AI-provider execution have been validated.
