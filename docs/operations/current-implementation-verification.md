# SULY implementation verification

**Snapshot:** 2026-11-20  
**Working branch:** `main`  
**Supabase project:** `razvryvazmqvvqkzetuo`

## Remote migration history

| Version | Migration |
|---|---|
| 20261119231023 | suly_identity_foundation |
| 20261119232036 | profile_display_name_metadata |
| 20261119232226 | conversations_messages_foundation |
| 20261119232329 | bump_conversation_on_message |
| 20261119232400 | tighten_message_client_insert |
| 20261119232535 | assistant_reply_idempotency |
| 20261119232854 | tighten_profile_column_grants |

## Public tables

| Table | RLS | Policies | Access |
|---|---:|---:|---|
| profiles | enabled | 2 | Authenticated owner only |
| conversations | enabled | 4 | Authenticated owner only |
| messages | enabled | 2 | Authenticated owner only |

Anonymous SELECT access is not granted to these tables. Profile owners can update only `display_name`, `avatar_url`, and `locale`; owner IDs and timestamps are server-managed. The authenticated client can insert only its own user messages; the database defaults the role to `user`, and the role column is not insertable by authenticated clients. Assistant, system, and tool messages are reserved for trusted server-side workers.

## Client implementation

- Supabase URL and publishable key are configured in the client. The publishable key is public by design; no service-role or provider secret is shipped to the client.
- Email/password sign-up and sign-in, sign-out, session restoration, and account state are wired.
- Expo SecureStore is used on Android/iOS; AsyncStorage is used on web.
- Profile lookup, conversation history, message listing, user-message insertion, conversation rename, and deletion use the signed-in user's RLS context.

## Server chat gateway

- The authenticated API route `POST /v1/chat/respond` verifies conversation and message ownership before processing a request.
- Assistant messages are inserted only by the server-side Supabase secret client; authenticated client roles cannot set the message role column.
- An OpenAI-compatible adapter exists, but `AI_PROVIDER=disabled` is the default. Both `/v1/chat/respond` and the worker `ai.respond` operation require the user's persisted `ai.provider.run` approval before a provider call. The tool catalog reports whether the provider is configured separately from whether the user approved it. No AI provider or paid service has been activated.
- A server-only `SUPABASE_SECRET_KEY` and optional `AI_API_KEY` are documented as environment variables; neither is committed to the repository or bundled into the client.

## Verification limits

- SQL metadata checks confirmed RLS flags, policy definitions, grants, triggers, indexes, and migration history.
- A real-user end-to-end auth/chat test has not been performed; no test user was created on the owner's behalf.
- Supabase email delivery and redirect allow-list have not been verified.
- Backend gateway tests were added, but the GitHub connector did not return a check/status record for the latest commits, so no new CI pass is claimed here.
- The Agent Workspace supports deterministic text analysis, approval-gated `ai.respond`, and the separately gated Hermes bridge. The Activity screen reads the authenticated task history API; task cards open a live detail view with step outputs, errors, polling, and cancellation. Failed tasks can be retried from the detail view up to two manual retries; the database RPC resets only failed steps and preserves completed checkpoints.
- The bounded manual retry migration (`20261120130500_bounded_manual_task_retry.sql`) has been committed but must still be applied to Supabase before the retry endpoint can work in the live project. It adds a two-retry limit per task and a service-role-only RPC.
- Provider configuration, API deployment, streaming, durable worker execution, and native production builds remain pending.


## Engine run ledger update (2026-11-20)

- Added `supabase/migrations/20261120153000_engine_run_ledger.sql` to create an owner-readable, service-written per-attempt `engine_runs` ledger and lease-guarded start/finish RPCs.
- Added the server-side `EngineRunStore` adapter and connected the approved Hermes operation to record running/succeeded/failed/cancelled states. No prompt, output, provider key, or approval scope is stored in the ledger.
- The authenticated task-detail API now returns owner-filtered engine attempt history, and the Expo task detail screen renders engine ID, attempt number, status, timestamps, and safe error code.
- The migration is committed to GitHub but has NOT been applied to Supabase. Hermes and the worker remain disabled by default; this update does not start or deploy either service.
- A terminal engine-run transition requires the same unexpired step lease token. A stale worker cannot mark a newer attempt as complete.

## Engine-run crash reconciliation update (2026-11-20)

- Added `supabase/migrations/20261120170000_engine_run_reconciliation.sql`. A PostgreSQL trigger closes only the matching still-running engine attempt when its owning task step leaves `running`, loses its lease token, expires, or is cancelled.
- Lease expiry is recorded as the safe error code `engine_lease_expired`; other unexpected step transitions use `engine_step_ended`. Explicit cancellation records `cancelled` without storing diagnostic payloads.
- The trigger does not change task or step state, delete history, store prompts/outputs/secrets, or overwrite engine attempts already in a terminal state.
- Added the Arabic learning guide `docs/learning/ENGINE_RUN_LIFECYCLE_AR.md` describing the task/step/attempt/lease model and the related source files.
- This migration is committed to GitHub but has NOT been applied to Supabase. A PostgreSQL integration test against a disposable database is still required before production use.
- CI verification for commit `78a8b22949b3165d262ba139f2dc8f6c754aabdd`: Repository baseline checks passed; Platform CI passed both API tests and client typecheck/web export. The newly added migration and guide still need their own post-commit CI run.
- No worker, Hermes runtime, provider, or production service was enabled or deployed by this change.


## Hermes native Runs API integration update (2026-11-20)

- The Compose build context and runtime README now use the audited immutable Hermes revision `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`; the earlier unresolved pin was replaced.
- The SULY bridge now uses native `POST /v1/runs`, bounded status polling through `GET /v1/runs/{run_id}`, and cooperative stop through `POST /v1/runs/{run_id}/stop`.
- Each SULY engine attempt supplies a stable `Idempotency-Key` derived from its engine-run UUID. The returned opaque Hermes run ID is stored through the lease-guarded `attach_engine_upstream_run` RPC.
- Added migration `20261120173000_engine_upstream_run_identity.sql`; it is committed but NOT applied to the live Supabase project.
- Added `HERMES_AGENT_ISOLATION_CONFIRMED=false`. The bridge refuses to run unless explicitly attested, but this flag is not a sandbox and must remain false until a per-task runtime manager and its isolation controls are implemented and verified.
- Added `docs/learning/HERMES_RUN_LIFECYCLE_AR.md` with the Arabic explanation of the flow and file responsibilities.
- Verification on commit `f7ab085f2d7d69c7bd41dea4c3e4c486864eddc9`: API compile and tests passed. Client typecheck/web export was still running at the time of this snapshot; check the latest Actions run before claiming full CI success.
- No live Hermes runtime, provider, Worker, or production API was enabled. SSE forwarding, remote-run recovery after SULY restart, per-task runtime orchestration, and real container security testing remain pending.
