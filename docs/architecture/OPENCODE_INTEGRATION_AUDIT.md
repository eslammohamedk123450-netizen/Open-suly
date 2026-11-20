# OpenCode integration and isolation audit

Audit date: 2026-11-20

## Source identity

- Upstream repository: `anomalyco/opencode`
- Immutable revision: `4cca18d80450a3dd6a9a4142028bde84ccb3116e`
- Server package: `@opencode/server` version `2.3.0`
- License: MIT (root LICENSE and package metadata inspected)
- This audit does not copy or modify upstream source.

## Findings from the pinned source

### Authentication is server-wide, not SULY-user authentication

- `packages/server/src/middleware/authorization.ts` validates one configured server password or a server-signed session cookie.
- `packages/server/src/auth.ts` issues a 30-day session token derived from that server password. It does not map a credential to a SULY user, task, or tenant.
- The server authorization layer is therefore a perimeter gate for one OpenCode server, not a tenant isolation boundary.

### Sessions and locations are not SULY tenant scopes

- `packages/server/src/handlers/session.ts` resolves session IDs through the server's Session service and performs session/form ownership checks within that server.
- `packages/server/src/middleware/session-location.ts` resolves a session's location and provides location-specific services; it does not bind a session to a SULY user.
- `packages/server/src/location.ts` accepts a working directory from query/header (or process cwd) and resolves location services. A caller must never be allowed to choose an arbitrary host path.
- OpenCode's native session IDs and its internal location scoping cannot replace SULY's task ownership, workspace authorization, or lease checks.

### The server process owns a broad execution surface

The server package wires filesystem, shell, persistent PTY, worktree, MCP, credentials, plugins, automation, jobs, and session services. A shared server process would create a large cross-task attack surface even if SULY hides session IDs.

## Required SULY integration design

OpenCode remains disabled and unavailable until all of the following are implemented and tested:

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


## Per-attempt sandbox command hardening — 2026-11-20

The existing non-executing Docker command policy was tightened before any runtime manager is allowed to call it:

- Container name and immutable labels now bind to both SULY task UUID and engine-run UUID. Retries of one task therefore receive distinct runtime identities.
- PID, IPC, and UTS namespaces are explicitly private; restart policy is disabled.
- Docker container logs are disabled by default to reduce accidental persistence of prompts, command output, and credentials. Structured SULY audit metadata remains the control-plane responsibility.
- Existing defaults remain: digest-pinned image only, no network, read-only root filesystem, all Linux capabilities dropped, no-new-privileges, seccomp default, non-root UID/GID, bounded CPU/memory/PIDs/tmpfs, one private workspace mount, no host mounts, and no Docker socket.
- Production provisioners must pass the persisted engine_run_id. The task_id fallback is retained only for existing policy tests and must not be used by a real provisioner.
- The command builder does not execute Docker and does not enforce wall-clock timeout itself. A future runtime supervisor must enforce timeout, cleanup on cancellation/lease loss/restart, and daemon-level isolation before any engine can be enabled.
- Unit tests cover per-attempt names/labels and private namespaces. This is policy construction testing only, not a container escape or cross-tenant integration test.


## SULY-side lease contract progress — 2026-11-20

A fail-closed contract now exists in `services/api/app/services/runtime_broker_contract.py`:

- Runtime lease binds canonical task UUID, engine-run UUID, engine ID, runtime UUID, one endpoint host, opaque access token, and a maximum one-hour expiry.
- The broker rejects a previously leased task attempt and rejects runtime ID reuse within its process lifetime, including after release.
- The endpoint must use HTTPS, contain no embedded credentials/query/fragment/path, and match one exact DNS host in the explicit allowlist. IP literals are rejected, including metadata-service addresses.
- Access tokens are bounded and excluded from dataclass repr.
- Context-managed sessions always attempt release; a failed/unconfirmed release remains counted as active.

Tests cover task/run/engine binding, endpoint allowlisting, IP-literal and HTTP rejection, credential bounds, expiry, duplicate attempts, runtime reuse, invalid provider leases, and teardown.

This is only an in-process validation contract around a provider protocol. There is still no concrete runtime provider, container launch, task-scoped broker service, network policy, or live OpenCode integration. The catalog remains disabled.


## Broker contract checkpoint — 2026-11-20

- Added `services/api/app/services/runtime_broker_contract.py` with RuntimeLease, RuntimeLeaseProvider protocol, and TaskScopedRuntimeBroker.
- The contract binds a lease to one task, one engine run, and one engine; requires an explicit runtime host allowlist; hides access credentials from repr; limits lease lifetime to one hour; rejects runtime ID reuse and repeated acquisition of the same attempt; and attempts teardown through a context manager.
- Tests cover host allowlisting (including metadata/localhost targets), task/run mismatch, expiry, credential redaction, teardown, and cross-attempt runtime reuse.
- This is not a concrete provider and does not start or stop Docker/OCI containers. OpenCode remains disabled. No server process, session, shell, PTY, MCP, plugin, or filesystem operation is reachable from SULY yet.


## Pinned API and permission protocol review — 2026-11-20

Additional source files reviewed at the same immutable upstream revision:

- `packages/server/src/auth.ts`
- `packages/server/src/middleware/authorization.ts`
- `packages/server/src/handlers/session.ts`
- `packages/server/src/handlers/permission.ts`
- `packages/server/src/handlers/event.ts`
- `packages/protocol/openapi.json`
- `packages/core/test/permission.test.ts`

### Authentication and session scope
- OpenCode's HTTP auth is Basic auth with the configured username `opencode` and server password. It also accepts a server-signed session cookie and, for some routes, an `auth_token` query parameter. SULY must use the Authorization header only; never place a runtime secret in a URL or expose a pairing link/cookie to the client.
- If no password is configured, the authorization middleware allows requests. A provisioned runtime must fail startup unless a unique high-entropy password has been configured.
- Password-derived session cookies are long-lived (30 days) and are not a SULY tenant credential. Do not create or retain these cookies in SULY.
- `POST /api/session` can create a session and accept an explicit permission ruleset. The upstream permission tests confirm an unmatched permission defaults to `ask`; an explicit catch-all `{action: "*", resource: "*", effect: "ask"}` makes the fail-closed intent visible and testable.
- Session permissions can be answered with `once`, `always`, or `reject`. SULY's adapter must expose only `once` and `reject`; never forward `always` or saved permission mutations.
- The permission handler verifies that a request belongs to the session ID in the route. SULY must additionally bind that session ID to exactly one engine_run_id and worker lease in its own database before forwarding.

### Event and message data handling
- `GET /api/event` is a server-wide event stream, not a per-session stream. It can include permission requests, tool lifecycle, tool input, text/reasoning deltas, PTY and filesystem events, and plugin/MCP events.
- The upstream stream is explicitly volatile: disconnected consumers can miss events. It is not a durable task ledger.
- SULY must parse events and allowlist only coarse lifecycle metadata and exact permission-request identity. Never forward raw event envelopes, tool input, arguments, reasoning, text deltas, terminal output, filesystem paths, or plugin/MCP payloads into the general task feed.
- Permission requests should be fetched from the session-scoped permission endpoint and checked for matching sessionID; the event stream is only a notification that a state change occurred.
- Prompt/session APIs accept files, skills, agents, metadata, shell, and other advanced payloads. Until their authorization and content scanning contracts exist, SULY should send text-only prompts and not forward client-selected local paths, file URIs, skills, agent IDs, or metadata.

### Adapter policy before implementation
1. Require a unique per-attempt server password and a verified HTTPS runtime lease origin from SULY's exact allowlist.
2. Create one OpenCode process and private data directory per engine run, with no shared database/session directory.
3. Create exactly one root session for the run with explicit catch-all ask permissions; do not expose session list/fork/import/move APIs to the client.
4. Persist the opaque session ID under the same task/run/lease guard before sending a prompt. A failure to persist the ID must interrupt/tear down the newly created session.
5. Reply only to a permission request that belongs to that session and is still pending. Permit only once/reject and recheck the lease immediately before the upstream call.
6. Use the SSE stream as a notification channel only; poll the session-scoped permission list and message endpoint for state, then reduce outputs through a separate bounded sanitizer.
7. No shell/PTY/MCP/plugin/network capability is enabled merely by adding the HTTP adapter. Runtime policy must independently enforce deny-by-default egress and workspace boundaries.

### Current implementation status
- The source review and this policy are documentation only.
- The SULY runtime lease contract exists, but there is still no concrete OpenCode provisioner, per-attempt process, OpenCode API client, durable session-ID column/RPC, output reducer, or permission UI.
- OpenCode remains disabled. No OpenCode server or session was started.
