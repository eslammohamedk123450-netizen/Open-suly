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

## Public tables

| Table | RLS | Policies | Access |
|---|---:|---:|---|
| profiles | enabled | 2 | Authenticated owner only |
| conversations | enabled | 4 | Authenticated owner only |
| messages | enabled | 2 | Authenticated owner only |

Anonymous SELECT access is not granted to these tables. The authenticated client can insert only its own user messages; the database defaults the role to `user`, and the role column is not insertable by authenticated clients. Assistant, system, and tool messages are reserved for trusted server-side workers.

## Client implementation

- Supabase URL and publishable key are configured in the client. The publishable key is public by design; no service-role or provider secret is shipped to the client.
- Email/password sign-up and sign-in, sign-out, session restoration, and account state are wired.
- Expo SecureStore is used on Android/iOS; AsyncStorage is used on web.
- Profile lookup, conversation history, message listing, user-message insertion, conversation rename, and deletion use the signed-in user's RLS context.

## Server chat gateway

- The authenticated API route `POST /v1/chat/respond` verifies conversation and message ownership before processing a request.
- Assistant messages are inserted only by the server-side Supabase secret client; authenticated client roles cannot set the message role column.
- An OpenAI-compatible adapter exists, but `AI_PROVIDER=disabled` is the default. No AI provider or paid service has been activated.
- A server-only `SUPABASE_SECRET_KEY` and optional `AI_API_KEY` are documented as environment variables; neither is committed to the repository or bundled into the client.

## Verification limits

- SQL metadata checks confirmed RLS flags, policy definitions, grants, triggers, indexes, and migration history.
- A real-user end-to-end auth/chat test has not been performed; no test user was created on the owner's behalf.
- Supabase email delivery and redirect allow-list have not been verified.
- Backend gateway tests were added, but the GitHub connector did not return a check/status record for the latest commits, so no new CI pass is claimed here.
- Provider configuration, API deployment, streaming, durable worker execution, and native production builds remain pending.
