# SULY isolated OpenCode Runtime Provisioner

Private control-plane component. It owns Docker access and must run on a dedicated worker host/VM with a dedicated Docker daemon. Never mount the Docker socket into the public API, web app, or task containers.

## Interfaces

- `POST /v1/runtimes`: SULY-authenticated runtime creation from a bounded workspace snapshot; returns a one-time runtime token and HTTPS gateway URL.
- `DELETE /v1/runtimes/{runtime_id}`: SULY-authenticated release with exact task/run ownership.
- `/v1/runtime-gateway/{runtime_id}/...`: task-token-authenticated allowlisted OpenCode API proxy. Container port remains loopback-only.
- `POST /v1/runtime-gateway/{runtime_id}/execute`: create/reuse a session and submit a bounded prompt to the original OpenCode server.
- `GET /v1/runtimes/{runtime_id}/results`: export bounded UTF-8 workspace files; symlinks, secrets, .git, node_modules and binary files are excluded.
- `POST /internal/cleanup`: SULY-authenticated expiry cleanup.

Runtime ownership, container mapping, token hashes and expiry are stored in SQLite. Raw per-runtime tokens are returned only on creation and are not stored.

## Configuration

- `SULY_PROVISIONER_TOKEN`: high-entropy service credential (at least 32 characters).
- `RUNTIME_GATEWAY_ORIGIN`: public HTTPS origin of this service.
- `OPENCODE_RUNTIME_IMAGE`: immutable `repository@sha256:<64 hex>` image built from `engines/opencode/Dockerfile`.
- `RUNTIME_DB_PATH`: persistent volume path (default `/var/lib/suly-runtime/runtimes.sqlite3`).
- `RUNTIME_WORKSPACE_ROOT`: persistent workspace path.

Terminate TLS at a trusted reverse proxy/load balancer. The public SULY API connects to the private provisioner endpoint over TLS. Docker only publishes OpenCode on 127.0.0.1.

## Mandatory production controls

1. Use a dedicated VM and restrict Docker socket access to this service. Docker socket access is effectively host-root.
2. Apply host firewall egress restrictions: allow only approved AI gateway/provider endpoints and DNS; block metadata IPs, private control-plane ranges, host management ports and Docker endpoints. Per-task bridge networks alone are not an egress firewall.
3. Configure TLS, request rate limits, body limits and DDoS protection at ingress.
4. Persist and encrypt SQLite/workspace volumes; do not run multiple replicas with independent local SQLite stores. Multi-host deployments require a shared transactional lease store and distributed watchdog.
5. Results are a bounded UTF-8 snapshot; binary files, symlinks and files over 1 MiB are omitted. SULY must apply results against the recorded workspace revision and show a reviewable diff before changing canonical project files.
6. The gateway uses HTTP only on loopback between gateway and container. Public access must always be HTTPS.

## Run

```sh
pip install -r requirements.txt
export SULY_PROVISIONER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export RUNTIME_GATEWAY_ORIGIN="https://runtime-gateway.example.com"
export OPENCODE_RUNTIME_IMAGE="registry.example/opencode@sha256:<digest>"
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

The service must have access to its dedicated Docker daemon. Build the OpenCode image from repository root with `engines/opencode/Dockerfile`.

## Verification

```sh
pip install pytest httpx
PYTHONPATH=. pytest -q tests
```

Tests use fake Docker clients and API validation tests. They do not establish that production TLS ingress, host firewall, real Docker daemon or a full AI-provider execution have been validated.
