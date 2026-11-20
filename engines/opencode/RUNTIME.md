# OpenCode runtime image

This Dockerfile builds the **pinned upstream OpenCode 2.3.0 monorepo** as a standalone runtime image. It does not copy OpenCode into the SULY FastAPI process.

## Build

Run from the SULY repository root after initializing and verifying the submodule:

```bash
git submodule update --init --recursive engines/opencode/upstream
python engines/opencode/verify_upstream.py
docker build -f engines/opencode/Dockerfile -t suly-opencode:2.3.0 .
```

The build installs the upstream workspace with `bun install --frozen-lockfile`, runs as UID/GID 10001, and starts the original CLI server on container port 4096. No host port is published by this Dockerfile.

## Required runtime contract

A production provisioner must create a **fresh container for each task attempt**, not reuse a shared long-lived OpenCode process across tenants. It must:

- Mount only that attempt's workspace at `/workspace`; never mount the Docker socket, host root, home directories, or another tenant's files.
- Supply a unique high-entropy `OPENCODE_SERVER_PASSWORD` at runtime through a secret channel; never bake it into the image, compose file, logs, or task prompt.
- Place the container on a private per-runtime network and expose port 4096 only to the SULY broker.
- Apply non-root execution, read-only root filesystem where compatible, bounded tmpfs, CPU, memory, PID, disk and wall-clock limits, and an outbound network policy.
- Keep provider credentials scoped to the task and inject them only through the approved runtime secret interface.
- Revoke credentials and destroy the container and workspace after completion, cancellation, timeout, or lease loss.
- Verify the runtime lease and tenant/task mapping before every broker request. A container being reachable is not authorization.

## Current limitation

This image is a reproducible build recipe, **not a runtime provisioner**. SULY still needs a durable session-to-task/run/lease mapping and a Docker/runtime provider that enforces globally unique runtime identity, process-tree teardown, network policy, and crash cleanup. Do not enable OpenCode for end-user tasks until those controls and the end-to-end tests exist.

## Pinned 2.x API operations currently exposed by the SULY transport

The adapter follows the pinned 2.3.0 protocol shapes:

- `GET /api/info`: bounded server version probe.
- `POST /api/session`: create a session with all permissions defaulting to `ask`.
- `GET /api/session/:sessionID/permission`: list pending session-owned approvals.
- `POST /api/session/:sessionID/permission/:requestID/reply`: only one-time approval or rejection is expressible.
- `POST /api/session/:sessionID/prompt`: durably admit a text-only prompt (`{ "text": ... }`).
- `POST /api/session/:sessionID/interrupt?resume=false`: request interruption without automatically resuming queued work.
- `GET /api/skill` and `GET /api/provider`: bounded metadata catalogues only.

Prompt admission and interrupt transport are not yet exposed through user-facing API routes. They must be called only after a durable SULY mapping proves the session belongs to the current user, task, engine run, and unexpired runtime lease. The response is untrusted and must be correlated to the same task attempt before persistence.
