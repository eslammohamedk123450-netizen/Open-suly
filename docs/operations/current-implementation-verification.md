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
