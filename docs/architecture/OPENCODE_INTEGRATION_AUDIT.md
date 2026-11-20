# OpenCode integration and isolation audit

Audit date: 2026-11-20

## Source identity

- Upstream: https://github.com/anomalyco/opencode
- Pinned revision: `4cca18d80450a3dd6a9a4142028bde84ccb3116e`
- Server package: `@opencode/server` version `2.3.0`
- License: MIT (root LICENSE and server package metadata inspected)
- No upstream source has been copied or modified by this audit.

## Findings from the pinned source

### Authentication is server-wide, not SULY-user authentication

- `packages/server/src/middleware/authorization.ts` validates one configured server password or a server-signed session cookie.
- `packages/server/src/auth.ts` issues a 30-day session token derived from that server password. It does not map a credential to a SULY user, task, or tenant.
- The server authorization layer is therefore a perimeter gate for one OpenCode server, not a tenant isolation boundary.

### Sessions are scoped to server instance/location, not to SULY tenants

- `packages/server/src/handlers/session.ts` resolves session IDs through the server's Session service and performs session/form ownership checks within that server.
- `packages/server/src/middleware/session-location.ts` resolves a session's location and provides location-specific services; it does not bind a session to a SULY user.
- `packages/server/src/location.ts` accepts a working directory from query/header (or process cwd) and resolves location services. A caller must never be allowed to choose an arbitrary host path.
- OpenCode's native session IDs and its internal location scoping cannot replace SULY's task ownership, workspace authorization, or lease checks.

### Process responsibilities are broad

The server package wires filesystem, shell, persistent PTY, worktree, MCP, credentials, plugins, automation, jobs, and session services. A shared server process would create a large cross-task attack surface even if SULY hides its session IDs.

## Required SULY integration design

OpenCode remains disabled and unavailable until all of the following exist and are tested:

1. A dedicated ephemeral runtime/container per SULY task attempt (not merely a per-session directory).
2. A pinned image digest and immutable OpenCode revision, non-root user, read-only base filesystem, bounded writable task workspace, and CPU/memory/PID/disk/time limits.
3. No host mounts, no Docker socket, no inherited host credentials, no shared PTY, no shared process, and no shared OpenCode database/session store between tenants.
4. The SULY control plane creates the workspace from an allowlisted source, maps it to exactly one task and lease, and never accepts arbitrary host paths from the client.
5. OpenCode's server password is generated per runtime, delivered only to the task-scoped broker, short-lived where possible, and never sent to the mobile/web client or logged.
6. Every request is mediated by a broker that checks task owner, active task/run, lease, runtime identity, and allowed route before forwarding.
7. Tool execution, shell, MCP, plugin, PTY, and filesystem access are disabled by default or restricted by a task-specific policy. Egress is default-deny through an SSRF-safe proxy.
8. Runtime teardown revokes credentials and removes the task workspace according to retention policy; cleanup must also run after timeout, cancellation, lease loss, and worker restart.
9. Integration tests prove two tasks cannot read each other's files, sessions, messages, process state, environment, credentials, or network destinations.

## Current decision

- Keep the OpenCode catalog entry as `disabled`; do not create a shared server or route user traffic to the upstream server.
- Do not claim the engine is integrated or usable. The audit establishes upstream API/authentication facts and the isolation contract only.
- The next implementation unit is the task-scoped runtime provisioner and broker contract, followed by sandbox policy tests. It must remain opt-in and must not launch containers until separately approved.
