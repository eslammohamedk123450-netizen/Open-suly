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
