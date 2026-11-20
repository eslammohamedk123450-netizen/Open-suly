# Hermes sessions, skills, and toolsets integration audit

Audit date: 2026-11-20

## Source identity

- Upstream: `NousResearch/hermes-agent`
- Immutable revision: `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`
- License: MIT
- This is a source audit only; no upstream source is copied or launched.

## Skills endpoint

- `GET /v1/skills` is bearer-authenticated by Hermes' `_require_auth` middleware.
- It enumerates installed skills with `find_all_skills(skip_disabled=False, include_editorial=True)`, so the list may include disabled/editorial skills.
- Listing a skill does not establish that it is safe, enabled for a SULY user, or permitted to execute.
- Skill metadata/content must be treated as untrusted supply-chain input. A skill can include instructions and may reference tools, scripts, or external services.
- SULY must keep skill discovery separate from skill activation. Any future catalog is read-only metadata, filtered against an image-pinned allowlist and license review. Skills must not self-enable tools or receive credentials.

## Toolsets endpoint

- `GET /v1/toolsets` is also bearer-authenticated.
- It reads the API server's Hermes configuration and returns enabled/configured toolsets and their expanded tool names.
- This reflects the configuration of one Hermes server process, not SULY per-user authorization. It can expose operational configuration metadata and must never be called by the mobile/web client.
- SULY's own tool registry and approval ledger remain authoritative. A Hermes toolset being enabled/configured does not grant it to a SULY task.

## Sessions API

- The native `/api/sessions` routes are bearer-authenticated and operate on the Hermes profile's local session database.
- Session IDs, source/title fields, parent/child relationships, and profile-scoped storage are native Hermes resources. They are not bound to SULY user IDs, task IDs, RLS, or SULY ownership.
- The session response intentionally hides full system prompts and model configuration, but the session API still exposes messages, metadata, fork, chat, and lifecycle operations within that Hermes profile.
- A shared Hermes profile/server would therefore create a cross-tenant data and execution boundary risk even when SULY stores different run IDs.
- Native session persistence also conflicts with the current SULY runtime target of one ephemeral isolated runtime per task attempt.

## SULY integration decision

1. Do not expose Hermes `/api/sessions` directly to the client or proxy it through a shared Hermes server.
2. SULY's own conversation/session tables remain the sole tenant-scoped source of truth. Build each task prompt from explicitly authorized SULY conversation context.
3. Do not persist native Hermes session IDs across task attempts while runtimes are ephemeral. A future persistent per-tenant runtime requires a separate security review and isolation model.
4. Skill listing may later be exposed as read-only metadata from a fixed, image-pinned catalog after license, provenance, and content review. Disabled/editorial skills are not executable capabilities.
5. Do not enable Hermes tools or toolsets merely because upstream reports them enabled/configured. The SULY adapter must intersect requested tools with the task-specific allowlist and persisted approvals.
6. No native Hermes session, skill, or toolset integration is currently enabled. Worker and Hermes remain disabled by default.

## Next implementation gates

- Immutable skill manifest with repository/revision/license/hash and explicit allowed capability set.
- Parser and validator that reject unreviewed skill sources and metadata.
- SULY conversation-context builder with size limits and ownership/RLS checks.
- Tests proving no native Hermes session ID or toolset configuration crosses a SULY tenant boundary.
