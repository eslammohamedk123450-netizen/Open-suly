# OpenCode task lifecycle integration

This layer is the SULY control plane around the pinned upstream OpenCode server. It does not replace or fork OpenCode's own engine implementation.

## Components

- `OpenCodeTaskExecutor`: captures an owner-scoped project snapshot, obtains a task-attempt runtime, invokes OpenCode, registers the session, and persists a reviewable change set.
- `TaskScopedRuntimeBroker`: validates the exact HTTPS origin and task/run identity. Successful executions retain their runtime lease until the change set is applied/rejected; failed executions release immediately.
- `OpenCodeApprovalManager`: lists upstream permission requests for the exact session and dispatches only one-time allow or reject. Permanent `always` grants are deliberately unsupported.
- `OpenCodeEventConsumer`: consumes the original `GET /api/event` SSE stream, reduces events through the pinned upstream protocol contract, and persists only session-bound lifecycle metadata.
- `OpenCodeLifecycleStore`: stores runs, events, approvals and change sets in Supabase using the server-only client.
- `opencode_tasks` router: owner-scoped run/event/approval reads, permission decisions, change-set inspection, and explicit apply/reject.
- `apply_opencode_change_set` SQL RPC: performs a transactional compare-and-swap against the project workspace revision before applying file changes. A stale workspace is rejected; no blind overwrite occurs.

## Runtime configuration

The API runtime broker is opt-in. Configure all of the following on the API server:

- `RUNTIME_PROVISIONER_URL`: HTTPS origin of the private Runtime Provisioner.
- `RUNTIME_PROVISIONER_TOKEN`: server-only bearer credential.
- `RUNTIME_PROVISIONER_ALLOWED_ORIGINS`: JSON array containing the exact approved HTTPS origin(s), e.g. `["https://runtime.example.com"]`.
- `RUNTIME_PROVISIONER_TIMEOUT_SECONDS`: optional, default 10.

The runtime provisioner separately requires `SULY_PROVISIONER_TOKEN`, `RUNTIME_GATEWAY_ORIGIN`, `OPENCODE_RUNTIME_IMAGE` pinned to an immutable SHA-256 digest, and persistent paths for its SQLite database and workspace.

Do not expose the Docker socket, runtime token, Supabase secret key, or container host ports to web/mobile clients.

## API surface

- `GET /v1/projects/{project_id}/opencode/runs`
- `GET /v1/opencode/runs/{run_id}/events`
- `GET /v1/opencode/runs/{run_id}/approvals`
- `POST /v1/opencode/approvals/{approval_id}/decision` with `{"decision":"once"}` or `{"decision":"reject"}`
- `GET /v1/opencode/change-sets/{change_set_id}`
- `POST /v1/opencode/change-sets/{change_set_id}/decision` with `{"decision":"apply"}` or `{"decision":"reject"}`

All user-facing routes require the authenticated SULY user and apply owner filters. The runtime broker must be configured on the API process for live permission refresh and replies.

## Database migrations

Apply in order after reviewing the existing project migrations:

1. `20261121010500_opencode_task_lifecycle.sql`
2. `20261121011000_opencode_atomic_changeset_apply.sql`

The tables have RLS enabled. Authenticated users receive read-only access to their own task metadata; writes and the atomic apply RPC are reserved for the trusted `service_role` backend. These migrations are committed to the repository; they have **not** been applied to a live Supabase project in this work session.

## Recovery and operational limits

The runtime lease registry remains process-local, but the provisioner derives a stable per-runtime access credential with HMAC-SHA256 from the server-only provisioner secret and the canonical runtime/task/run IDs. Only the credential digest is stored in SQLite. After an API process restart, a trusted API worker can recover the same lease through the owner-bound recovery endpoint using the persisted `runtime_id`; concurrent API instances can reconstruct the same credential without rotating it or persisting plaintext tokens.

This recovers access to a still-live runtime, but it does not by itself resume a lost worker's Python call stack or guarantee exactly-once prompt execution. Durable worker heartbeats, task reconciliation, and safe retry semantics remain required before claiming seamless recovery across worker crashes.

The runtime gateway forwards `GET /api/event` as a true streaming response instead of buffering an unbounded SSE connection. When `OpenCodeTaskExecutor` is invoked with a lifecycle store, it persists the runtime ID immediately, creates and persists the upstream session before submitting the prompt, and starts a bounded cancellable SSE consumer concurrently with execution. The event consumer stops after the prompt returns or the execution path fails.

Task containers use an internal Docker network with outbound egress disabled by default. If an operator enables `RUNTIME_ALLOW_EGRESS=true`, the dedicated runtime host must also enforce the documented outbound firewall allowlist; this environment flag alone is not a firewall.

The generic `TaskWorker` remains a callback-based RPC adapter. A dedicated deployed worker entrypoint that claims OpenCode steps and invokes `OpenCodeTaskExecutor` has not yet been wired or exercised end-to-end; the lifecycle executor and callbacks are implemented, but queue-to-engine dispatch, worker deployment, and multi-worker recovery still need a dedicated integration test.

The CI Docker smoke test starts the pinned OpenCode image and checks `/api/info`. It is not a multi-tenant concurrency test and does not prove host firewall policy, production TLS termination, or a complete LLM-backed task execution. Those require a dedicated runtime host and an explicitly configured model provider.
