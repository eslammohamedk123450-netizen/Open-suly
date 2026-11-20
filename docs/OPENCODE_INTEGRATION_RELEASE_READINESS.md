# OpenCode integration: release readiness and one-server deployment

## Product target

SULY owns identity, projects, task orchestration, quotas, approvals, billing and the user-facing experience. The pinned upstream OpenCode process is a coding engine only. The browser/mobile client never connects to an OpenCode port directly.

## Implemented repository building blocks

- Pinned upstream source and provenance verification under `engines/opencode/`.
- Bounded HTTP transport requiring a task-attempt `RuntimeLease`; fixed route allow-list, HTTPS origin validation, Basic Auth, no redirects, no ambient proxy, bounded response bodies.
- Fail-closed permission mapping: only one-time approval or rejection is expressible.
- Durable owner-scoped OpenCode session mapping in `public.opencode_sessions`; no runtime URL, access token, prompt or model output is stored in this table.
- Owner/project-scoped session metadata read endpoint.
- Bounded project snapshot builder from canonical `project_files` rows; excludes .env files, VCS metadata and dependency/cache directories; enforces 200 files, 256 KiB per file and 5 MiB total.
- HTTPS runtime-provisioner adapter. It calls a fixed, allow-listed HTTPS origin and never accesses Docker or a host socket.
- Unit tests for session ownership, provisioner failure modes and workspace snapshot boundaries.
- CI includes these new tests and the pinned upstream verification/build.

## Four implementation groups

### A. Projects and durable sessions

The migration `20261121020000_opencode_durable_sessions.sql` creates the owner-bound session mapping. The upstream session is registered only after the runtime has been acquired and the upstream session has been created. The composite foreign keys prevent attaching another user's project, task or engine run. The API exposes metadata only.

Still required before enabling end-user execution:
- Add a worker-owned orchestration flow that creates the upstream session, then registers it using the current task lease.
- Persist session activity and status transitions from validated upstream events.
- Add explicit cleanup/expiry reconciliation for abandoned mappings.
- Add integration tests against a disposable Postgres/Supabase environment.

### B. Runtime and workspace execution

The runtime provisioner adapter is a client contract, not a container manager. A separately deployed trusted provisioner must implement the documented API and enforce:
- New container and workspace for every task attempt.
- Unique runtime IDs and lease tokens, short expiry, atomic acquire/release.
- Non-root UID, no Docker socket, no host mounts, read-only root FS, bounded writable workspace/tmpfs, CPU/memory/PID/disk/time limits.
- Private broker-only ingress and explicit egress policy.
- Secret injection at runtime only; revoke credentials and destroy process tree/container on completion, cancellation, timeout and lease loss.
- Crash recovery and idempotent teardown.

Do not implement a Docker socket client inside the public API service. Access to a Docker daemon is effectively host-admin access. Prefer a narrowly scoped provisioner service or an orchestrator with task-level isolation (for example, a dedicated container runtime service).

### C. Engine capabilities and result bridge

The current transport exposes health, session creation, prompt submission, interruption, permission listing/replies and bounded skill/provider catalog metadata. The next adapter work must add:
- A validated event stream with cursor/reconnect handling and duplicate suppression.
- Result and file-change retrieval correlated to the same user/task/run/lease.
- A two-phase workspace apply flow: generate patch in the sandbox, validate paths and size, present a diff, then apply only after user/task policy authorizes it.
- Explicit skills/agent selection from a reviewed allow-list. Never enable arbitrary plugins, MCP servers, shell, PTY or network access by copying upstream config blindly.
- Provider/model routing through the SULY server-side gateway without returning credentials to the engine UI.

### D. Release, integration and operations

Before a shared-server release:
- Run API tests, upstream typecheck, runtime image build, migration validation, security checks and end-to-end tests.
- Test two simultaneous users, two tasks for one user, cancellation races, worker crash, lease expiry, duplicate prompt submission, malicious project filenames, prompt injection in repository content and attempted cross-tenant access.
- Publish resource defaults and a single-server capacity profile. Queue work and limit concurrency to measured RAM/CPU; do not run every agent concurrently on a small host.
- Add structured logs with opaque IDs only; no prompts, file contents, access tokens or provider secrets.
- Add backup/restore and orphan-runtime cleanup runbooks.

## One-server operating model

One host may run the API, worker scheduler, Redis and a trusted runtime provisioner, while Supabase remains the managed identity/database/storage service. Coding tasks must run in isolated per-attempt containers, not in the API or general worker process. The provisioner must apply a global concurrency limit so low-resource hosts queue work instead of exhausting memory.

A single server is a deployment topology, not a reason to share one OpenCode process or filesystem across tenants.

## Release gates

OpenCode is **not production-ready** until all of the following are true:
1. A real provisioner is deployed and its acquire/release/crash-cleanup contract is integration-tested.
2. Session creation and mapping are invoked by the worker only after lease validation.
3. Workspace snapshots are mounted read-only initially; patches are reviewed and applied through an owner-checked server path.
4. Event/result bridge is durable, bounded, resumable and tenant-correlated.
5. All migrations are applied and RLS/security advisors are reviewed.
6. End-to-end isolation, cancellation, resource-limit and recovery tests pass.
7. Docker image build and full CI are green on the final commit.

The GitHub CI status is authoritative for code checks; a green unit-test run alone does not prove runtime isolation or production readiness.
