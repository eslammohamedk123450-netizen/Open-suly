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
