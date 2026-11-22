# OpenCode upstream engine

SULY pins the **complete upstream OpenCode repository** as a Git submodule at `upstream/`. It is built as a separate runtime image and dispatched through SULY's task-scoped engine adapter; it is not flattened into the FastAPI process and is not called as a hosted AI service.

## Provenance

- Upstream: https://github.com/anomalyco/opencode
- Pinned commit: `4cca18d80450a3dd6a9a4142028bde84ccb3116e`
- Upstream package version at the audited revision: `2.3.0`
- License: MIT (the original `LICENSE` is retained in the submodule)
- Upstream commit signature: verified by GitHub at import time
- Pin rationale: immutable revision audited in `docs/architecture/OPENCODE_INTEGRATION_AUDIT.md`. Do not silently advance to the moving `dev` branch.

## Build the original source

From the SULY repository root:

```bash
git submodule update --init --recursive engines/opencode/upstream
git -C engines/opencode/upstream rev-parse HEAD
```

The result must equal the pinned commit above. The upstream monorepo includes the original server, core, AI/provider integrations, CLI, protocol/schema, plugin system, browser plugin, TUI, skills, tests, build scripts, and documentation.

The upstream workspace uses Bun `1.4.4`. Build from the upstream repository root with its own lockfile and workspace scripts; copying only `packages/server` is incomplete. The dedicated CI workflow verifies both pinned upstream revisions, runs the SULY adapter contracts, typechecks the original OpenCode server, and builds the OpenCode, Hermes, and SULY provisioner images. It does not start those images unless the separate runtime-smoke repository variable is explicitly enabled. The live Docker server smoke test is gated behind `SULY_ENABLE_ENGINE_RUNTIME_SMOKE=true` for the later external acceptance phase.

## Runtime and security boundary

The upstream server has a broad filesystem, shell, PTY, MCP, plugin, and credential surface. SULY therefore provisions one isolated runtime per task attempt and routes requests only through that attempt's authenticated runtime lease. The API worker does not receive a Docker socket, and the upstream server is never exposed directly to mobile/web clients.

SULY remains authoritative for user identity, tenant ownership, project snapshots, task/lease state, tool permissions, approvals, audit, usage, and secrets. Never pass Supabase service credentials or arbitrary host paths into OpenCode. Keep the engine disabled until the runtime provisioner and per-task isolation controls are deployed and verified.

## SULY task adapter

- `OpenCodeTaskExecutor` snapshots only the authenticated owner's bounded project workspace and starts the original OpenCode server through the attempt-scoped runtime broker.
- The durable run/session store records owner/project/task/engine-run/runtime identity. Permission requests are reduced to sanitized metadata and bound to the exact run/session/lease.
- Permission decisions are limited to `once` or `reject`; permanent `always` grants are not representable. SULY approvals remain authoritative.
- SSE is treated as volatile progress, not a durable task ledger. Only allowlisted event metadata is persisted; prompts, reasoning, tool arguments, terminal output, filesystem paths, and raw event envelopes are discarded.
- The executor validates changed-file paths and SHA-256 digests, then stores a reviewable change set against the captured project revision. Applying is a separate owner action and the database apply function rejects stale revisions.
- Applying an initial change set queues one durable post-apply review step against the updated workspace. That review is read-only; any proposed fixes become a new change set and still require owner approval. The review step is marked with its source change-set ID so it cannot recursively enqueue more reviews.
- When OpenCode is a delegated child, its handoff remains active while a change set awaits owner decision and through the post-apply review. The parent receives the final applied/rejected/stale outcome before it resumes. Cancellation prevents a pending change set from being applied.

## Upstream update policy

Any upstream update requires:
1. Review the new commit and security advisories.
2. Re-run license and dependency review.
3. Update the gitlink pin and `UPSTREAM.json` together.
4. Re-run adapter, isolation, and engine build checks.

## Verification boundary

Repository CI covers adapter contracts, owner-scoped lifecycle APIs, permission transport, change-set validation, cancellation guards, the runtime provisioner contract/security tests, and upstream typecheck/image build where triggered. Static SQL invariant tests do not prove PostgreSQL execution. No hosted runtime, real model inference, production Supabase migration, cross-tenant isolation acceptance, or full live task execution is claimed in this code-completion phase; these belong to the later non-production/external acceptance test.
