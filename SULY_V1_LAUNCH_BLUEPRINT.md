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
- No worker process is deployed yet; queued tasks remain queued until a worker runtime is added and deployed.
- No DAG planner or model-generated plan is enabled yet.
- Worker claim/lease renewal, heartbeat, retry scheduling, checkpoint commits, and cooperative cancellation still need implementation and concurrency tests.
- Task API requires a deployed FastAPI service with server-only Supabase secret credentials.
- No provider key or paid service has been configured.

The task database foundation is live, but it must not be described as autonomous execution until workers are deployed and tested.
