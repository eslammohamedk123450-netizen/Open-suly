# SULY — Product Delivery Plan

This roadmap applies to the standalone SULY product.

## Phase 1 — Brand shell and app foundation
- Preserve the SULY name, logo/monogram, domain, and Midnight Gold design language.
- Build the responsive home screen, task composer, settings screen, navigation, cards, and buttons.
- Establish shared theme tokens, Arabic RTL, English LTR, and web/Android/iOS routing.
- Verify TypeScript and Expo web export.

**Exit:** app shell renders and navigation works on supported targets.

## Phase 2 — Supabase and identity foundation
- Create the first SULY schema with profiles and secure account lifecycle.
- Configure Auth providers and redirect URLs for the official domain.
- Apply RLS and test cross-user isolation.
- Add private file storage policies.

**Exit:** sign-up, sign-in, session refresh, sign-out, and profile ownership pass tests.

## Phase 3 — Conversations and direct chat
- Create conversation/message domain tables.
- Implement streaming-capable API contracts and message persistence.
- Add server-side provider gateway and safe error handling.

**Exit:** a signed-in user can exchange messages and only access their own conversations.

## Phase 4 — Task and agent foundation
- Define task plans, DAG steps, checkpoints, worker leases, retries, cancellation, and idempotency.
- Add a bounded worker runtime and tool registry.
- Add approval gates and execution audit trails.

**Exit:** a multi-step task can resume after interruption and produce an accurate status report.

## Phase 5 — Research, files, and tools
- Add web research, private file handling, document creation, and data analysis.
- Add isolated coding execution only after sandbox boundaries are tested.
- Add integrations through explicit user authorization.

**Exit:** each tool has permission checks, timeouts, limits, and tests.

## Phase 6 — Usage, plans, and administration
- Add server-authoritative usage ledger and configurable product plans.
- Add admin workflows with role-based access and audit logs.
- Add operational metrics and provider health monitoring.

**Exit:** usage is idempotent, auditable, and cannot be manipulated by the client.

## Phase 7 — Release hardening
- Test web, Android, and iOS builds.
- Complete RLS, auth, rate-limit, secret-handling, and abuse tests.
- Add backups, incident procedures, and deployment health checks.
- Publish only after release criteria pass.

**Exit:** release candidate has reproducible builds, passing checks, and documented operational readiness.

## Rules
- Work on `main` only.
- No paid recurring service without explicit approval.
- Never report a test or deployment as successful without evidence.
- Work sequentially; record blockers and continue with independent work where safe.

## Verified implementation snapshot — 2026-11-20

### Implemented
- Expo client now initializes the connected Supabase project with its public publishable key.
- Email/password sign-up, sign-in, sign-out, session restoration, and account state are wired in the client.
- Native sessions use Expo SecureStore; web sessions use AsyncStorage.
- New accounts receive a profile row through the Auth trigger. The client reads the profile under owner-only RLS.
- Conversation and message tables are live. The client can create, list, rename, and delete its own conversations and persist user messages.
- Client inserts default to the `user` message role. Authenticated clients cannot set the role column or write assistant/system/tool messages; those are reserved for trusted server-side execution.
- RLS and role grants were checked against the live database. All three public tables have RLS enabled; anonymous reads are not granted.

### Not yet verified / still pending
- End-to-end sign-up, email confirmation, sign-in, session refresh, and sign-out with a real test account.
- Auth redirect allow-list and email delivery configuration in Supabase.
- Automated TypeScript/Expo CI result for the latest authentication and conversation commits.
- Provider configuration and real assistant responses, streaming, and durable task execution.
- Android/iOS production builds.

The app must continue to describe saved user messages as saved messages, not as completed AI responses, until the API is deployed, a provider is configured, and authenticated end-to-end tests pass.

### Chat API foundation
- An authenticated `POST /v1/chat/respond` endpoint now validates that the requested conversation and user message belong to the signed-in user.
- Assistant replies are written by the server only; the public client cannot assign assistant/system/tool roles.
- A unique database index prevents duplicate persisted assistant replies for the same user message.
- An OpenAI-compatible provider adapter is implemented, but `AI_PROVIDER` defaults to `disabled`. No provider has been selected and no provider key has been added.
- The API requires a server-only Supabase secret key to perform trusted assistant-message writes. That key is intentionally absent from the repository and client bundle.

The chat endpoint is a non-streaming first slice. It is not considered operational until the API is deployed, server secrets are configured, a provider is deliberately selected, and authenticated end-to-end tests pass.


## Verified implementation snapshot — durable task foundation (2026-11-20)

### Implemented
- Added `public.tasks` for durable task requests, lifecycle state, idempotency keys, bounded attempts, cancellation requests, result checkpoints, and timestamps.
- Added `public.task_steps` for ordered DAG steps, dependency declarations, per-step input/output checkpoints, retry counters, and expiring worker lease fields.
- Enforced owner-scoped RLS on both tables. Authenticated users can read only their own task records; task mutations are server-only.
- Restricted client column privileges so worker lease owner/token/expiry fields are not readable from the public client.
- Added authenticated API routes to enqueue tasks idempotently, list a user's tasks, inspect a task and its steps, and request cancellation.
- Added API boundary tests for unauthenticated access, missing server credentials, and blank task requests.
- Added forward-only migrations matching the live Supabase migration versions:
  - `20261119233548_durable_tasks_dag_foundation`
  - `20261119233650_tighten_task_read_permissions`

### Not yet implemented / verified
- An opt-in polling worker runtime and one deterministic allow-listed handler exist, but no worker process is deployed or running on a host.
- The bounded DAG plan API is implemented; model-generated planning is not enabled yet.
- Live multi-worker concurrency, lease-expiry, retry-timing, cancellation, and populated-task integration tests are still pending.
- Task API requires a deployed FastAPI service with server-only Supabase secret credentials.
- No provider key or paid service has been configured.

The task database foundation is live, but it must not be described as autonomous execution until workers are deployed and tested.


## Task planning implementation — 2026-11-20

- Added `POST /v1/tasks/{task_id}/plan` to persist a bounded plan of 1–50 steps.
- Step keys must be unique; dependencies must refer only to previously declared steps, enforcing a deterministic acyclic order.
- Planning is committed atomically by the Postgres `plan_task` function; partial plans cannot be left behind if validation or insertion fails.
- The function is SECURITY INVOKER, revoked from public/anon/authenticated, and executable only by service_role. It locks the owned task row and only accepts a task that is still queued and has no existing steps.
- Migration: `20261119233958_atomic_task_planning`.
- API tests cover authentication, duplicate keys, and forward/cyclic dependency rejection.
- This phase creates and validates execution plans; the subsequent worker lease protocol is documented below.


## Worker lease runtime — 2026-11-20

### Implemented and applied
- Applied migration version `20261119234304_worker_lease_runtime` to the connected Supabase database.
- Added atomic dependency-aware claims using `FOR UPDATE SKIP LOCKED`; a claim increments the bounded attempt counter and returns a short-lived opaque lease token.
- Added token-checked lease renewal and checkpoint completion. A stale or expired worker cannot commit output.
- Added bounded exponential retry scheduling, expired-lease recovery, terminal failure handling, and cooperative cancellation cleanup.
- All worker RPCs are SECURITY INVOKER; execution is revoked from public/anon/authenticated and granted only to service_role.
- Security advisor returned no lints after the migration.
- Added `services/api/app/services/task_worker.py`, a one-step trusted RPC adapter, plus unit tests for claim, completion, failure, invalid configuration, and stale leases.

### Still pending / explicitly not claimed
- No continuously running worker is deployed or hosted.
- Only the deterministic `text.analyze` handler is registered; no provider key or AI provider has been enabled.
- No live multi-worker race test or populated-task end-to-end execution test has run.
- Long-running handlers must renew their lease and stop immediately if renewal fails.
- The worker adapter is infrastructure, not yet an autonomous agent.


## Conversation API and first worker runtime — 2026-11-20

### Implemented
- Added authenticated conversation list/create endpoints.
- Added authenticated message history and user-message creation endpoints.
- Every conversation/message query is scoped by the verified user's ID; the server only accepts user-role message creation through this API.
- Added request limits and validation for pagination, conversation titles, and message content.
- Added an opt-in polling worker process with bounded idle backoff and graceful SIGINT/SIGTERM shutdown.
- Worker execution is allow-listed: the first built-in operation is deterministic `text.analyze`; unknown operations fail closed and enter the bounded retry path.
- Worker startup is disabled by default and requires server-only Supabase credentials. The API process does not silently start a worker.
- Added tests for conversation endpoint authentication/validation and worker operation allow-list behavior.

### Not yet deployed / verified
- The conversation API and worker runtime are source-complete but still require CI confirmation and a deployed FastAPI/worker runtime for end-to-end testing.
- The only built-in task operation is local text analysis; no web browsing, code execution, external integrations, or AI task handler is enabled.
- No AI provider has been selected or configured. The chat response route returns a clear unavailable response while the provider remains disabled.


## AI gateway hardening and chronological chat context — 2026-11-20

### Implemented
- AI gateway validates message count, allowed roles, non-empty content, and total prompt size before making a provider request.
- Provider requests enforce the configured timeout even when an injected HTTP client is used by tests or internal callers.
- Provider rate limits receive a safe retry-later error; raw provider response bodies and secrets are not exposed to clients.
- Malformed, empty, and oversized provider replies are rejected before persistence.
- Chat prompt construction now ends exactly at the requested user message. Later conversation turns are excluded when replying to an earlier message.
- Added deterministic tests for input bounds, invalid roles, timeout mapping, rate limiting, malformed/oversized outputs, and chronological context boundaries.

### Verification boundary
- These changes are committed to `main`; CI for this new commit set must complete before calling the new tests passing.
- No provider key was added, no paid provider was selected, and the AI gateway remains disabled by default.
- No live assistant generation or API deployment is claimed.


## Deterministic agent planning and execution bridge — 2026-11-20

### Implemented on main
- Added `app.services.agent_planner`, a deterministic planner with an explicit allowlist boundary.
- Current supported request syntax is `analyze: <text>` or `حلل: <text>` (also accepts `analyse:` and `حلّل:`). It produces exactly one `text.analyze` step.
- Added authenticated `POST /v1/tasks/{task_id}/auto-plan`. It loads the task under the authenticated owner, accepts only queued tasks, and persists the generated plan through the existing server-only atomic `plan_task` RPC.
- Unsupported general requests fail closed with HTTP 422; no fake generic plan is generated.
- Added worker-flow integration tests covering claim → lease renewal → allow-listed dispatch → token-checked checkpoint, plus rejection/failure of an unsupported operation.
- Added planner and API tests for Arabic/English prefixes, empty input, oversized input, authentication, and unsupported task types.

### Current execution boundary
- The only executable operation remains `text.analyze`; it computes character/word/line counts and a bounded preview.
- DAG dependency readiness, retries, cancellation, leases, and task terminal status are enforced by the existing database RPC protocol.
- The new tests simulate RPC responses; they do not constitute a live Supabase task execution test.
- No LLM-based planner, web search, browser, filesystem, code execution, or external connector tools are enabled.
- The worker remains opt-in and is not deployed or running as a hosted service.


## Tool registry foundation — 2026-11-20

### Implemented on main
- Added a central worker tool registry with explicit operation names, descriptions, permission-scope metadata, required/allowed input fields, input byte limits, and handler binding.
- Worker dispatch now resolves operations through this registry instead of a separate ad-hoc handler dictionary.
- Unknown operations, unexpected input fields, missing required fields, non-JSON input, duplicate registrations, and oversized inputs fail closed before execution.
- The only registered operation remains `text.analyze`; its input contract is limited to a text string. No shell, browser, filesystem, web-search, or external-provider capability was added.

### Verification boundary
- Automated tests cover registry metadata, duplicate registration, schema enforcement, size limits, and rejection of unsupported operations.
- Permission-scope values are metadata only; no user-consent grant system is claimed yet.
- No external tool, paid service, API key, deployment, or database migration was introduced.


## Tool authorization gate and planner capability sync — 2026-11-20

### Implemented on main
- Added a trusted `ToolExecutionContext` carrying approved permission scopes. It is created by trusted server code and is never read from task input.
- Registry tools require approval by default. A tool can bypass the approval gate only when explicitly marked safe for approval-free local execution; the existing pure `text.analyze` operation is the only such tool.
- Sensitive registered operations fail closed unless the trusted execution context contains the exact required scope.
- Task payloads cannot self-grant permissions: approval fields are not accepted as tool input.
- The deterministic planner now checks the worker registry before emitting a `text.analyze` plan, reducing planner/worker capability drift.

### Verification boundary
- Unit tests cover default-deny behavior, exact-scope authorization, no handler execution before approval, and rejection of self-granted scopes.
- This is an authorization gate interface, not yet a persisted user-consent workflow. No external tool is currently registered.
- No Supabase schema change, provider, API key, paid service, or deployment was introduced.
