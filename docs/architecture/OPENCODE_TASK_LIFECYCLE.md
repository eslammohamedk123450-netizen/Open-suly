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

The runtime lease registry is process-local. If the API process restarts, the in-memory lease token is lost; the provisioner still has its own TTL and Docker cleanup metadata, but the API cannot transparently resume an active permission exchange. Such a run must be reconciled as interrupted and its runtime allowed to expire or be explicitly reaped. A durable encrypted lease vault and worker-level heartbeat/reconciliation are still required for seamless recovery across API restarts.

The event consumer is a bounded component and the event feed is volatile. It must be run concurrently with prompt execution by the task worker to capture all events; reconnecting after a completed prompt cannot replay missed events. The current API route surfaces persisted events but does not itself start a background event-consumer task.

The CI Docker smoke test starts the pinned OpenCode image and checks `/api/info`. It is not a multi-tenant concurrency test and does not prove host firewall policy, production TLS termination, or a complete LLM-backed task execution. Those require a dedicated runtime host and an explicitly configured model provider.
