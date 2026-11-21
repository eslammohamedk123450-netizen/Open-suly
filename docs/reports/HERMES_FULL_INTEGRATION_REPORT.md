# SULY — Hermes Full Integration Report
## Execution checkpoint 01 — repository and upstream audit

**Report status:** IN PROGRESS — NOT A COMPLETION CERTIFICATE  
**Audit date:** 2026-11-21  
**Repository:** `eslammohamedk123450-netizen/Open-suly`  
**Audited base branch:** `main`  
**Audited base commit:** `5e109500ce0665802fac68a51e048832fb01e704`  
**Hermes upstream:** `https://github.com/NousResearch/hermes-agent`  
**Pinned Hermes revision:** `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`

> This is the first execution checkpoint. It records repository facts and the verified implementation boundary. It does not claim that Hermes is running, that all capabilities are integrated, or that production readiness has been achieved.

## 1. Executive summary

The current `main` branch already contains a substantial Hermes integration foundation. It is materially beyond a simple source pin or a one-shot chat bridge:

- Hermes upstream is pinned to an immutable commit and built from its original Dockerfile as a separate runtime.
- SULY has a native Hermes Runs API adapter with idempotent admission, bounded status polling, cooperative stop, lease-guarded upstream run identity, metadata-only SSE reduction, and owner-scoped progress/approval/steering routes.
- Hermes task execution is represented by an approval-gated worker operation.
- SULY's durable task/step lease remains authoritative; the worker rejects late results after lease loss.
- OpenCode has a separate upstream source/runtime integration path. The current roadmap records its core code integration as closed, while staging/runtime activation remains gated.
- No Hermes runtime, model provider, live tool execution, or production sandbox has been verified.

Subsequent execution checkpoints on `main` have added task-scoped runtime leases, opaque runtime identity persistence/recovery, approval and steering recovery, orphan cleanup, teardown-before-success gating, a mandatory Hermes runtime profile, bounded conversation continuity, owner-scoped project workspace snapshots, metadata-only subagent visibility in the task UI, and read-only skills/toolset discovery.

The remaining blockers are now narrower but still production-critical: there is no runtime-provisioner implementation/deployment in this repository; the external provider has not demonstrated enforcement of `suly-hermes-task-v1`; the additive Supabase migrations have not been applied to staging/production; and persistent Hermes sessions, long-term memory, skill source/install/update, MCP credential brokering, SULY-owned child-task budgets/cancellation, and unified provider routing remain incomplete.

## 2. Initial repository state

The audited repository is public and writable by the connected GitHub identity. Its default branch is `main`. The repository-level `AGENTS.md` and architecture documents require work directly on `main`; this checkpoint follows that repository rule and does not create a parallel branch.

The latest audited `main` commit is:

- `5e109500ce0665802fac68a51e048832fb01e704`
- Commit message: `docs(roadmap): mark OpenCode code integration closed and staging gated`
- Parent: `a5bfb31ab9a79bd707a44aea99d7b2a92f0119dc`

The repository contains:
- `engines/hermes/` — Hermes compose profile and upstream/runtime documentation.
- `engines/opencode/` — OpenCode Docker/runtime/provenance files and pinned upstream submodule.
- `services/api/app/services/` — engine registry/contracts, Hermes adapter, run store/reconciler, runtime broker contract, agent planner/manager.
- `services/api/app/routers/` — task, agent, tool-approval, and OpenCode routes.
- `supabase/migrations/` — durable tasks, approvals, engine run ledger/events, project workspace, and OpenCode lifecycle migrations.
- `services/api/tests/` — Hermes, worker, approval, runtime broker, engine, and OpenCode tests.

## 3. Hermes upstream provenance

| Item | Audited value |
|---|---|
| Upstream repository | `NousResearch/hermes-agent` |
| Exact revision | `2de9f51b8008a7d49a49221c184f2f11cbfc4af1` |
| License at pinned revision | MIT |
| License notice | Must be preserved if source is vendored or redistributed |
| Build strategy in SULY | Remote immutable Docker build context; upstream Dockerfile |
| Python compatibility | Upstream declares Python `>=3.11,<3.15`; keep its runtime separate from the SULY API environment |
| Security model | Upstream explicitly describes Hermes as single-tenant and identifies OS-level whole-process isolation as the boundary against adversarial model output |

Upstream source areas confirmed during this audit include:
- `gateway/platforms/api_server.py`
- `gateway/platforms/api_server_runs.py`
- `gateway/platforms/api_server_memory_sessions.py`
- `tools/delegate_tool.py` and the delegate tool modules
- `tools/memory_tool.py`
- `tools/skill_manager_tool.py`
- `tools/mcp_tool.py` and MCP lifecycle/discovery modules
- `skills/`, `providers/`, `cron/`, and the broader `tools/` package.

The upstream API route table includes native Runs API operations, skills discovery, session list/create/read/update/delete, session messages/fork/chat, and model locking. The API capability document reports memory-write API as disabled. Do not infer that every upstream CLI or in-process feature is remotely exposed by the API.

## 4. Existing SULY implementation — audited

### 4.1 Hermes source and runtime packaging

**IMPLEMENTED IN REPOSITORY**
- Immutable upstream commit pin in `engines/hermes/compose.yaml` and `engines/hermes/README.md`.
- Original upstream Dockerfile is used; Hermes is not imported into the FastAPI process.
- Opt-in Compose profile `agent-engines`.
- No published host port.
- API server hard-disabled by default.
- Separate named Hermes data volume and private Compose network.
- No Supabase service key or SULY admin secret is supplied to Hermes.

**NOT VERIFIED**
- Image build/start in this execution environment.
- Whole-process sandbox behavior under a real deployment.
- Per-task runtime creation, global uniqueness, crash cleanup, and cross-tenant isolation.
- CPU, memory, PID, disk, and network-egress enforcement.

### 4.2 Native Runs API adapter

**IMPLEMENTED IN REPOSITORY**
- Native `POST /v1/runs` admission.
- Idempotency key derived from the SULY engine-run attempt.
- Bounded polling of `GET /v1/runs/{run_id}`.
- Cooperative `POST /v1/runs/{run_id}/stop`.
- Lease-guarded persistence of opaque upstream run IDs.
- Optional SSE consumer with strict event-name/run-ID validation and metadata reduction.
- Owner-scoped task progress, bounded steering, and exact-request approval details/decisions.
- Only one-time approval and denial are exposed; permanent/session-wide grants are not exposed.
- Worker cancellation and lease-loss signals are connected to the adapter.

**LIMITS**
- Upstream stop is cooperative; acknowledgement is not proof of process termination.
- Reconciliation and remote run state recovery must be proven against an actual runtime.
- Event persistence requires the committed Supabase migrations to be applied and validated before deployment.
- No live Hermes API has been called from SULY in the audited state.

### 4.3 Worker, engine registry, and SULY control plane

**IMPLEMENTED IN REPOSITORY**
- Engine contract and metadata registry.
- Agent role catalog/manager and capability lookup.
- Approval-gated `hermes.agent.turn` operation.
- Input/output bounds and server-side configuration gates.
- Durable SULY task/step leases, retry/cancel/checkpoint foundations.
- Engine-run ledger and owner-filtered event history.
- Runtime lease validation contract for external provisioners.

**LIMITS**
- The registry is not itself a runtime provisioner.
- A runtime lease contract is not a Docker/container implementation.
- SULY must remain the authority for user identity, task ownership, approvals, quotas, audit, usage, and result acceptance.

### 4.4 OpenCode preservation

The current repository roadmap records OpenCode core code integration as closed for its current scope, with a pinned upstream executor path, project/task integration, review/apply flow, and CI evidence on prior commits. Runtime activation and staging remain gated. Hermes work must not replace or merge OpenCode's source, runtime, session, permission, or workspace boundaries.

## 5. Capability matrix and next implementation gates

| Capability | Current repository status | Required next work |
|---|---|---|
| Original Hermes source | Immutable remote source pin; original Dockerfile | Full source/component inventory, transitive license/dependency audit, update policy |
| Core agent runtime | Native Runs API adapter exists; runtime disabled | Per-task whole-process sandbox and live adapter contract verification |
| Skills discovery | Upstream `GET /v1/skills` route exists; no SULY skill adapter/UI | Owner/project scope, provenance, allow-listed discovery, safe install/update review |
| Skill execution | Native Hermes tool capability exists upstream | Restrict to reviewed skills inside the task sandbox; audit execution and output |
| Persistent memory | Upstream memory tools/provider exist; no SULY-owned memory bridge | Tenant/project namespace, retention, export/delete, retrieval policy, injection safety |
| Sessions/history | Upstream session APIs exist; current SULY adapter is run-centric | Durable SULY-to-Hermes session mapping, owner checks, session lifecycle, reset/expiry |
| Subagents/delegation | Upstream delegate tool and lifecycle events exist | Bounded depth/concurrency/budget, task contracts, child-run correlation, cancellation |
| Tool registry | SULY tool approval registry exists | Map approved SULY scopes to a minimal Hermes toolset; no blanket tool exposure |
| MCP | Upstream MCP client/tooling exists | SULY broker, server allow-list, per-tenant credentials, resource/time limits, audit |
| Provider system | Upstream provider support; SULY provider selection disabled | Server-side gateway adapter, no committed keys, provider-neutral configuration |
| Cron/automation | Upstream cron exists; SULY scheduler/control plane is authoritative | Re-express schedules through SULY task ledger; do not expose upstream cron directly |
| Browser/terminal/files | Upstream tools exist | Separate specialist runtimes or whole-process sandbox; default-deny network and filesystem |
| Orchestrator/collaboration | SULY planner/worker/engine foundations exist | Typed task/delegation/result contracts, conflict-safe artifacts, cross-engine review workflow |
| Supabase | Additive migrations committed | Disposable/staging apply, RLS/RPC verification, migration status evidence |
| Frontend | Task progress and approval UI exists | Skill/session/delegation visibility only after backend contracts are complete |
| Deployment | Compose scaffold exists | Real provisioner, hardened per-task image, resource/egress policies, health/cleanup runbooks |

## 6. Security findings that block activation

1. Hermes upstream is a single-tenant personal agent. One shared process must not be treated as a multi-tenant boundary.
2. The current SULY Compose file is a disabled development scaffold, not a verified per-task sandbox.
3. A terminal backend alone does not isolate Hermes' Python process, code-execution subprocess, MCP subprocesses, plugins, hooks, or imported skills.
4. The upstream API server exposes powerful tool capabilities, including terminal execution. A strong API key does not replace OS-level isolation.
5. The current `HERMES_AGENT_ISOLATION_CONFIRMED` setting is an operator attestation gate; it does not create or prove isolation.
6. No engine receives Supabase service credentials, raw database access, or permission-grant authority.
7. Skills/plugins/MCP content is untrusted executable input. Scanners are review aids, not a security boundary.
8. User/project memory must not share a process-global namespace or persistent volume across tenants.

**Activation remains disabled until whole-process isolation, task-scoped storage, default-deny egress, resource limits, process-tree teardown, and real cross-tenant/cancellation tests are verified.**

## 7. Database and deployment state

The repository contains additive migrations for engine runs, upstream run identity, run reconciliation, event history, approval metadata, project workspace, and OpenCode lifecycle. The architecture/status documents explicitly state that several engine migrations are committed but not applied to the live Supabase project.

No remote database migration was applied during this audit. Do not run destructive reset operations. The next database step is a disposable/staging application and verification of:
- RLS and owner-scoped reads;
- service-role-only write RPCs;
- lease validation on all engine-run writes;
- idempotent event sequence handling;
- approval request identity and one-time decision constraints;
- migration ordering and schema compatibility.

## 8. Validation evidence and non-claims

- The repository contains Hermes-specific API tests and worker/approval/runtime contract tests.
- This execution checkpoint did not run Python tests, TypeScript checks, Docker builds, container smoke tests, or Supabase migrations.
- GitHub combined status for the latest documentation commit reports a Railway service context failure. This is not a substitute for the repository's CI workflows and does not establish a Hermes code failure.
- Prior roadmap documentation records green Platform CI and upstream OpenCode verification on earlier code commits. Those results are not evidence for Hermes runtime readiness.
- No real provider/model was selected or configured.
- No production runtime was started.
- No user data or production service was changed.

## 9. Required next batches

1. **Complete upstream source audit:** inspect every top-level package and toolset at the exact pin; inventory file paths, license notices, dependencies, execution model, exposed APIs, and SULY disposition.
2. **Runtime provisioner:** implement or integrate a trusted per-attempt whole-process provisioner; no Docker socket inside the public API; acquire/release/recover/expiry/cleanup contract.
3. **Hermes adapter lifecycle:** bind each SULY task/step/attempt to a runtime and Hermes run; reconcile restart/lease-loss/cancel/stop outcomes.
4. **Skills adapter:** discovery/catalog first; installation and updates require source provenance, code review, checksums, and explicit approval.
5. **Session and memory adapter:** owner-scoped durable mapping; isolated memory namespaces and deletion/retention semantics.
6. **Delegation/subagents:** bounded child task contracts, budget/depth/concurrency limits, result validation, and parent-child cancellation.
7. **MCP/provider bridge:** per-user/project configuration and credentials, server-side only; no automatic provider selection.
8. **Collaboration layer:** structured handoff and artifact/change-set review between Hermes and OpenCode; no concurrent writes to the same workspace.
9. **Frontend integration:** expose only verified status and capabilities; no UI claims for disabled features.
10. **Final verification and delivery:** run all available checks, stage migrations in a disposable database, build and smoke-test isolated runtimes, and complete the final report.

## 10. Readiness assessment

| Readiness level | Current assessment |
|---|---|
| IMPLEMENTED | Partial: source pin, disabled runtime scaffold, Runs API adapter, worker approval/cancellation wiring, progress/approval/steering paths, durable run/event foundations |
| CODE VERIFIED | Not established by this checkpoint; requires CI on the exact resulting commits |
| INTEGRATION TESTED | Not established for a live Hermes runtime |
| RUNTIME TESTED | No |
| PRODUCTION TESTED | No |
| Safe to enable Hermes for user tasks | **No — keep disabled** |
| OpenCode source/runtime work preserved | Yes; do not alter its independent integration |
| Overall Hermes integration | **IN PROGRESS** |

This report must be updated after every implementation batch. The final report may be marked complete only when each claim is backed by code references and exact test/runtime evidence.


## 11. Execution checkpoint 02 — read-only Skills Discovery vertical slice

**Committed on `main`:**
- `d3ab9eab3062bdab0f43c90a949bb005323bd1f1` — add bounded Hermes catalog adapter.
- `9dddfd0bf5cc334925ce251ea471ccbd3951812e` — expose authenticated `GET /v1/agents/hermes/skills`.
- `baa6a4114797a1f9357ce74d44d5c3d5fb593d5b` — add catalog adapter tests.
- `26feb391ad622df187c00fb8a4e7b2897e34813b` — reject traversal-like skill identifiers.
- `c8323740e120a68170afeefbbb10c970c3607399` — add traversal regression coverage.

### Implemented

- Added `services/api/app/services/hermes_catalog.py`.
- Reads only the pinned Hermes `GET /v1/skills` catalog endpoint.
- Requires both Hermes feature enablement and the isolation-attestation gate; also requires server-side URL and API key configuration.
- Uses a fixed GET route, bounded timeout, no ambient proxy inheritance, no redirects, and a 256 KiB response ceiling.
- Validates the upstream list envelope and caps catalog size at 500 entries.
- Returns only `name`, `description`, and `category`; drops source paths and all other upstream fields.
- Removes control characters, bounds text lengths, deduplicates names, and rejects absolute/traversal-like skill identifiers.
- Exposes the metadata through authenticated `GET /v1/agents/hermes/skills`.
- Upstream errors are redacted; no source content, install, update, or execution operation is exposed.

### Deliberate limits

- This is **discovery only**. It does not load or execute skills, install or update skills, write into Hermes storage, or grant tool permissions.
- Skill descriptions are untrusted text and must be rendered as inert text by clients.
- The endpoint remains unavailable while Hermes is disabled or isolation is unconfirmed.
- The isolation setting is still an operator assertion, not proof of a per-task whole-process sandbox.

### Verification

- Added `services/api/tests/test_hermes_catalog.py` for schema validation, size limits, safe URL handling, explicit enablement gates, redaction, bounded metadata, and authentication.
- The test file was authored and committed; **it has not been executed in this environment**.
- GitHub combined status for `c8323740e120a68170afeefbbb10c970c3607399` currently reports a pending Railway service status context. This is not a completed test result and does not establish CI success or failure.

### Updated capability state

| Capability | Updated status |
|---|---|
| Skills discovery | **CODE IMPLEMENTED — CI/runtime verification pending** |
| Skills source viewing | Not implemented |
| Skills validation/linting | Not implemented in SULY |
| Skills installation/update | Not implemented |
| Skills execution and usage ledger | Not implemented |
| Skills provenance/review workflow | Not implemented |
| Skill tenant/project/task scopes | Not implemented |

The overall integration remains **IN PROGRESS** and Hermes must remain disabled for user task execution.


## 12. Execution checkpoint 03 — read-only Toolset Discovery vertical slice

**Committed on `main`:**
- `9d414eaf7dee0562c183cb7100a6653d9db7b40b` — add bounded toolset catalog normalization and transport.
- `e2cc881faa8016ec85b9bbbfaf551a818dfae657` — expose authenticated `GET /v1/agents/hermes/toolsets`.
- `072f1ffc92e6454460481f039fac93e5384c18d6` — add toolset discovery regression tests.

### Implemented

- Reused the same fixed-route, bounded, no-ambient-proxy metadata transport as Skills Discovery.
- Reads only Hermes `GET /v1/toolsets`.
- Returns toolset name, label, description, enabled flag, and validated tool identifiers.
- Does not return the upstream `configured` field, credentials, configuration, or arbitrary response fields.
- Validates platform identity, list size, toolset count, tool count, and tool identifier syntax.
- Exposes the metadata through authenticated `GET /v1/agents/hermes/toolsets`.
- Does not invoke any tool and does not modify Hermes configuration or permissions.

### Deliberate limits

- Toolset discovery is descriptive only. A listed or enabled upstream toolset is **not** permission for a SULY user to execute it.
- SULY's persisted approval registry and worker allow-list remain authoritative.
- Terminal, filesystem, browser, MCP, and other privileged capabilities remain blocked from user execution until per-task whole-process isolation and the SULY tool-scope bridge are verified.

### Verification

- Extended `services/api/tests/test_hermes_catalog.py` with toolset schema, metadata allow-list, route, and authentication tests.
- Tests are authored but **not executed in this environment**.
- GitHub combined status for `072f1ffc92e6454460481f039fac93e5384c18d6` currently shows a pending Railway service status context; it is not a completed CI test result.

### Updated capability state

| Capability | Updated status |
|---|---|
| Skills discovery | Code implemented; CI/runtime verification pending |
| Toolset discovery | **CODE IMPLEMENTED — CI/runtime verification pending** |
| Skill source viewing | Not implemented |
| Skills validation/linting | Not implemented in SULY |
| Skills installation/update | Not implemented |
| Skills execution and usage ledger | Not implemented |
| MCP discovery/broker | Not implemented in SULY |
| User-scoped memory/session bridge | Not implemented |
| Subagent/delegation task bridge | Not implemented |

The overall integration remains **IN PROGRESS**. Hermes user task execution remains disabled.


## 13. Execution checkpoint 04 — task-scoped runtime execution and control plane

### Implemented

- Hermes task execution now requires a `TaskScopedRuntimeBroker` and a runtime lease for the exact `task_id`, SULY engine-run ID, and `hermes-agent` engine ID.
- The worker acquires a separate runtime for each task attempt and releases it in a `finally` cleanup path.
- The Hermes adapter uses the lease gateway path and short-lived access token; it no longer needs the shared Hermes API key for this execution path.
- Lease validation checks the configured HTTPS origin allow-list, engine identity, task identity, engine-run identity, runtime ID, expiry, and gateway path.
- The worker persists only the opaque runtime UUID through the service-role RPC `attach_engine_runtime_identity`; it never stores the runtime access token.
- Added migration `20261121130000_engine_run_runtime_identity.sql` with a unique runtime identity index and active-step-lease guarded persistence RPC.
- Approval detail, approval resolution, and steering routes now recover a short-lived runtime credential through the trusted provisioner using the task/run/runtime identity.
- Those routes verify owner scope and the live worker lease before attempting runtime recovery.
- Added lease-aware stop operations and a runtime-aware engine stop reconciler. The reconciler can recover an orphaned Hermes runtime, request upstream stop when a run ID exists, and release the whole runtime process tree. It also handles the narrow window where a runtime exists before an upstream run ID is returned.
- Legacy shared-runtime run cleanup remains available for old rows that have an upstream run ID but no runtime ID.
- Added migration `20261121140000_engine_runtime_stop_recovery.sql` to reconcile/claim stale runs using either an upstream run ID or an opaque runtime ID.

### Security and lifecycle behavior

- No runtime token is stored in Supabase.
- Approval/steering requests do not accept a caller-supplied runtime URL, token, or runtime ID; the server obtains the runtime ID from the owner-scoped engine-run record.
- The provider's recover operation is bound to the exact runtime ID, task ID, engine-run ID, and engine ID.
- Runtime acquisition is rejected if the provider returns a mismatched lease.
- If upstream stop does not confirm, the reconciler still requests provider-side runtime release; only provider-confirmed release is counted as cleanup success.
- Worker-crash cleanup is now represented in code, but remains dependent on the external provisioner's recover/release semantics and TTL enforcement. Those semantics have not been runtime-tested.

### Verification

- GitHub Platform CI API test job for commit `3cfa01217043e5b798b76c588ccec57e8da7b443`: **646 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export for that commit was still in progress at the time of this report update.
- The following later commit `90c43a9a5d509c02c11d2a264b92c8e3ca676f86` adds legacy stop fallback for pre-existing shared-runtime rows; its CI run is pending.
- No migration was applied to the live Supabase project.
- No container/provisioner was started; no runtime isolation or process-tree teardown was verified in a deployed environment.

### Updated capability state

| Capability | Updated status |
|---|---|
| Per-task Hermes runtime lease | Code implemented; external provisioner contract required |
| Runtime identity persistence | Code + additive migration implemented; DB apply pending |
| Task-scoped approval details | Code implemented; CI passed at checkpoint commit |
| Task-scoped approval resolution | Code implemented; CI passed at checkpoint commit |
| Task-scoped steering | Code implemented; CI passed at checkpoint commit |
| Orphaned runtime stop/release | Code + additive migration implemented; runtime verification pending |
| Worker crash recovery | Code path implemented; depends on provisioner recovery/release guarantees |
| Production isolation | Not verified; do not enable user task execution until provisioner/runtime tests pass |

The overall integration remains **IN PROGRESS**. A green API test suite is not evidence of deployed container isolation.


## 14. Execution checkpoint 05 — outbound runtime transport hardening

### Implemented

- All Hermes Runs API, stop, steer, approval, and approval-detail HTTP clients now set `trust_env=False`; environment-provided HTTP(S) proxy variables cannot silently redirect runtime traffic.
- All those clients set `follow_redirects=False`; runtime credentials are not forwarded through an upstream redirect.
- The fixed metadata catalog transport already used the same proxy-free and redirect-free policy.
- Added a regression assertion for the main Hermes Runs API client configuration.

### Verification

- The Platform CI API job at commit `b3fdc7b6b02b3809b5ea35e15be3a2c147688466` passed after the transport hardening: **646 passed, 5 warnings**.
- Repository baseline checks for that commit passed.
- Later commits extend the event schema and are tracked in checkpoint 06 below.

## 15. Execution checkpoint 06 — bounded subagent lifecycle metadata

### Implemented

- The Hermes SSE reducer now projects only a strict metadata allow-list for `subagent.start` and `subagent.complete`.
- Accepted fields are opaque child/delegation/parent/session identifiers, bounded lifecycle status, bounded counters, and bounded duration.
- Child goals, summaries, prompts, tool arguments, reasoning, and output text remain excluded.
- `EngineRunStore.append_event` validates the metadata again at the persistence boundary and sends it through the service-role RPC as `p_metadata`.
- The existing migration `20261121150000_engine_run_subagent_metadata.sql` constrains persisted JSON keys, shapes, sizes, and event types.
- Added tests for safe projection, malformed identifiers, status/counter/duration validation, and exact metadata persistence.

### Scope boundary

This is **subagent lifecycle visibility**, not yet a SULY-owned child-task/delegation scheduler. Hermes upstream may execute its own delegated children inside the isolated parent runtime, but SULY still does not create separately budgeted child task rows, enforce a SULY child concurrency/depth budget, or independently cancel/reconcile each child. Those remain required before describing delegation as fully integrated.

### Verification

- Platform CI API tests at commit `7c01b0cc3818ea6d3fc1a9ba75766ad9de2d1b4a`: **661 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export for that commit: **passed**.
- No live Hermes runtime or actual subagent was executed.

## 16. Execution checkpoint 07 — stop-reconciler diagnostic RPC

A source audit found that `EngineRunStore.count_missing_upstream_identity()` called `count_engine_runs_missing_upstream_identity`, but no migration in the repository defined that RPC. Since `EngineRunReconciler.run_once()` calls the diagnostic before claiming stop work, this missing database function could prevent the reconciler loop from reaching its actual cleanup work after deployment.

### Implemented

- Added the missing function to `20261121140000_engine_runtime_stop_recovery.sql`.
- It accepts only a bounded age from 1 to 3600 seconds.
- It counts only stale `stop_pending` rows with neither an upstream run ID nor an opaque runtime ID; a valid task-scoped runtime identity is not misreported as missing.
- Execution is revoked from public/anon/authenticated and granted only to `service_role`.

### Verification and deployment boundary

- The API unit test for the RPC adapter is present and passed as part of the **661 passed** Platform CI run above.
- This verifies the Python adapter contract, not the SQL function against PostgreSQL.
- The migration remains committed but unapplied to the live Supabase project. A disposable/staging database migration and RPC execution test is still required.

### Updated capability state

| Capability | Updated status |
|---|---|
| Hermes outbound transport proxy/redirect hardening | Code + regression assertion; CI passed |
| Subagent event visibility | Code + tests + existing SQL allow-list migration; CI passed |
| SULY-owned child task/delegation orchestration | Not implemented |
| Missing-identity diagnostic RPC | Additive migration committed; PostgreSQL execution pending |
| Stop reconciler end-to-end | Code path implemented; DB apply and live provisioner verification pending |
| Hermes sessions and persistent memory bridge | Not implemented |
| MCP broker and per-tenant MCP credentials | Not implemented |
| Skills source review/install/update/execution bridge | Not implemented; discovery only |
| Provider gateway integration | Not implemented |
| Runtime provisioner implementation/deployment | External dependency; not available in this repository's current verified state |

The overall integration remains **IN PROGRESS**. The 661 passing API tests do not establish production isolation or completion of Hermes feature parity.


## 17. Execution checkpoint 08 — runtime teardown must precede engine success

A lifecycle review found that the Hermes worker previously marked an engine run `succeeded` before the `finally` block attempted to release its task-scoped runtime. If the provisioner did not confirm release, the engine ledger was already terminal and the orphan reconciler could not claim that runtime for cleanup.

### Implemented

- Hermes now attempts runtime release before writing any terminal engine-run status.
- A run is marked `succeeded` only after provider-confirmed runtime release.
- On execution failure or cooperative cancellation, the worker likewise records a terminal status only after runtime release is confirmed.
- If release is false or raises, the engine run remains `running` with its opaque runtime identity. The worker then fails/cancels the task step; the database step-transition trigger moves the still-open engine run to `stop_pending`, allowing the reconciler to recover and release the runtime.
- The same rule applies when runtime identity persistence is refused: the worker does not mark the engine run terminal if runtime cleanup remains unconfirmed.
- Added a regression test proving that an unconfirmed release cannot be reported as a successful Hermes engine run.

### Verification

- Platform CI API tests at commit `20bfe9171be3a8ff0d1aa132c604b16a1ae78a78`: **663 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export for that commit was still in progress when this checkpoint was recorded.
- This is mocked provider/worker verification. The external provisioner must still prove that release is idempotent and that recovery after worker crash can terminate the entire process tree.

### Updated lifecycle invariant

`engine_runs.status = succeeded` is now written only after the worker receives an affirmative runtime release result. If runtime teardown is uncertain, the engine run remains eligible for database-triggered `stop_pending` reconciliation instead of being prematurely finalized.

The overall integration remains **IN PROGRESS**. Runtime release semantics have not been tested against a deployed provisioner.


## 18. Execution checkpoint 09 — subagent progress reaches the SULY task UI

### Implemented

- The owner-scoped task detail endpoint now selects and returns the allow-listed `engine_run_events.metadata` JSON field.
- The client event type includes a metadata map.
- The task details screen renders bounded subagent identifiers, lifecycle status, task index/count, depth, tool count, and duration for `subagent.*` events.
- It does not display child goals, summaries, prompts, reasoning, tool arguments, or output content.
- Added an API regression fixture asserting the owner-scoped task response includes the safe subagent metadata.

### Verification

- Platform CI API tests at commit `585b408420ad97b23d76065d09e54ff60dcf280b`: **663 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export was still running when this checkpoint was recorded.
- This is UI visibility for upstream Hermes child lifecycle events; it does not implement SULY-owned child task records or independent child budgets/cancellation.

### Updated capability state

| Capability | Updated status |
|---|---|
| Hermes subagent event reduction | Implemented with allow-list; CI passed |
| Subagent metadata persistence | Implemented with SQL constraints; migration apply pending |
| Owner-scoped task API metadata | Implemented; API CI passed |
| Client subagent lifecycle display | Implemented; client CI pending |
| SULY-owned delegation/task graph per child | Not implemented |

The overall integration remains **IN PROGRESS**.


## 19. Execution checkpoint 10 — SULY conversation continuity for Hermes tasks

### Implemented

- Added optional `tasks.conversation_id` with a composite foreign key to `conversations(id, user_id)`; deleting a conversation clears only the task's context link and does not delete the task.
- The task creation API verifies that the selected conversation belongs to the authenticated user before persisting the link.
- The conversation screen now has a direct handoff to the Agent screen, carrying its conversation ID. The Agent screen defaults to Hermes for this handoff.
- The client includes the conversation ID when creating the durable task.
- Before a Hermes task begins, the worker loads up to 30 prior user/assistant messages from that exact owner-matched conversation, bounded by the task creation timestamp.
- The worker excludes system/tool messages, caps each included message, caps total history context at 8,000 characters, and keeps the full current task request within the Hermes prompt limit.
- The prompt labels conversation history as context, not system/developer instructions. If a real database read fails, the task fails closed instead of silently claiming that context was supplied.

### Session and memory boundary

- SULY's conversation ID is the logical session key. Each task still receives a fresh isolated Hermes runtime, so task process state and filesystem are not shared across attempts.
- Conversation history is copied as bounded context into each new task; this is not a persistent Hermes session and does not preserve an interactive Hermes process.
- This adds short-term conversation continuity only. A separate user/project memory store, memory extraction/retention controls, and memory injection policy remain unimplemented.

### Verification

- Platform CI API tests at commit `dd31092bc2aa699827fa250a7875f20caeb9a1c4`: **665 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export was still running when this checkpoint was recorded.
- The new migration is committed but has not been applied to the live Supabase project.

### Updated capability state

| Capability | Updated status |
|---|---|
| Conversation-to-Hermes handoff | Client/API code implemented; client CI pending |
| Owner-scoped task/conversation link | API + additive migration implemented; DB apply pending |
| Bounded conversation context | Worker implementation + tests; API CI passed |
| Persistent Hermes session | Not implemented; fresh runtime per task is intentional |
| Long-term user/project memory | Not implemented |

The overall integration remains **IN PROGRESS**.


## 20. Execution checkpoint 11 — Hermes skill and toolset discovery UI

### Implemented

- Added typed client API functions for the authenticated read-only Hermes skills and toolsets catalogs.
- The SULY Agent screen now displays up to 20 installed skill metadata entries and up to 20 toolsets, including their names, descriptions, categories, enabled flags, and bounded tool names.
- The UI explicitly labels this information as descriptive discovery only. It does not offer install, update, source editing, or tool execution controls.
- Upstream catalog strings remain inert text; the backend continues to normalize and size-limit the metadata.

### Scope boundary

- Catalog discovery still depends on the configured read-only Hermes catalog endpoint and may be unavailable when the legacy catalog sidecar is disabled.
- The catalog does not prove that a skill or toolset is present or enabled in a particular task-scoped runtime.
- Skill source inspection, signature/provenance review, install/update/uninstall, per-user skill storage, and execution grants remain unimplemented.

### Verification

- Platform CI API tests at commit `24849d405b21fb15bde3eb3882a6188fdfea7d2f`: **665 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export was still running when this checkpoint was recorded.

The overall integration remains **IN PROGRESS**.


## 21. Execution checkpoint 12 — Hermes project workspace snapshots

### Implemented

- Hermes task execution now checks whether the durable task is linked to a SULY project.
- For project-linked tasks, it uses the existing owner-scoped `ProjectWorkspaceStore` to create a deterministic, bounded snapshot.
- The worker passes only normalized `path`, `content`, and `sha256` entries into `TaskScopedRuntimeBroker.acquire(..., files=...)`.
- The workspace policy limits the snapshot to 200 files / 5 MiB, caps individual files at 256 KiB, caps paths at 240 characters to match the provisioner contract, and excludes reserved paths such as `.git`, `node_modules`, `.env*`, and `secrets/`.
- The project is re-verified against the task owner before any file rows are loaded. No host filesystem path is mounted or exposed to Hermes.
- Added a regression test proving the project snapshot is passed into the task-scoped Hermes runtime lease.

### Verification

- Platform CI API tests at commit `5b324305789bf4f6cf24a5a71168ea3e78bf93a7`: **670 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export was still running when this checkpoint was recorded.
- The external provisioner must still prove that it materializes the supplied files inside the correct isolated container and never into a shared host workspace.

### Updated capability state

| Capability | Updated status |
|---|---|
| Project-linked Hermes task | Implemented through existing Agent project context |
| Owner-scoped project snapshot | Reuses existing bounded ProjectWorkspaceStore |
| Runtime workspace file handoff | Implemented through lease provider contract |
| Provisioner materialization/isolation | Not runtime-verified |

The overall integration remains **IN PROGRESS**.


## 22. Execution checkpoint 13 — mandatory Hermes runtime security profile

### Implemented

- Added a versioned runtime profile identifier: `suly-hermes-task-v1`.
- The HTTPS provisioner receives this profile on Hermes runtime acquire and recover requests.
- The provisioner must echo the same profile in the returned lease.
- `RuntimeLease.validate` rejects Hermes leases with a missing or mismatched profile; the normal worker broker enforces this before the lease can be used.
- Orphan cleanup now recovers and releases Hermes leases through `TaskScopedRuntimeBroker`, so the same profile, identity, expiry, HTTPS-origin, gateway-path, and credential checks apply during cleanup.
- The profile contract requires a unique task runtime, no shared process/host filesystem, privileged toolsets disabled unless separately reviewed, default-deny network egress except the configured model gateway, resource limits, and complete process-tree teardown.

### Security boundary

The profile ID is an authenticated contract with the trusted provisioner, not cryptographic proof of OS-level enforcement. No provisioner implementation/deployment is present in this repository checkpoint, so Hermes must remain disabled until a provider that enforces this exact profile is deployed and verified.

### Verification

- Platform CI API tests at commit `60127ae64f308f6344a2fb2f1ece78e0c4e52c30`: **672 passed, 5 warnings**.
- Repository baseline checks for that commit: **passed**.
- Client typecheck/web export for that commit: **passed**.
- Tests cover profile request/response and rejection of unprofiled Hermes leases; they do not verify a live container's actual toolset/network policy.

### Updated capability state

| Capability | Updated status |
|---|---|
| Hermes runtime profile request | Implemented |
| Profile echo and lease validation | Implemented + tests |
| Profile validation during orphan cleanup | Implemented through task runtime broker |
| Actual toolset/network enforcement | External provisioner responsibility; not verified |
| Production Hermes activation | Blocked until profile-enforcing provisioner deployment |

The overall integration remains **IN PROGRESS**.


## 23. Execution checkpoint 14 — external runtime provisioner contract

### Implemented

- Added `docs/runtime-provisioner-openapi.yaml` describing the HTTPS provisioner acquire, recover, release, result retrieval, and task-scoped Hermes gateway routes.
- The contract specifies provisioner bearer authentication separately from the short-lived runtime lease bearer.
- The request/response schemas include task/run/engine identity, workspace snapshots, runtime profile echo, exact gateway path, lease expiry, and confirmed teardown result.
- Documented exact Hermes Runs API status/events/stop/steer/approval subroutes behind the per-runtime gateway.
- Linked the contract from `engines/hermes/README.md`.

### Boundary

This is an API contract, not the external provisioner implementation. No Docker/containerd controller, runtime gateway, token store, network policy enforcement, or deployment manifest has been added. The integration cannot be activated in production until a trusted provider implements this contract and passes the staging conformance/security tests.

The overall integration remains **IN PROGRESS**.


## 24. Execution checkpoint 15 — staging activation gate

Added `docs/HERMES_RUNTIME_PROVISIONER_ACTIVATION_CHECKLIST.md` as the operational gate for the external provider. It covers the dedicated host boundary, the mandatory `suly-hermes-task-v1` profile, toolset/network restrictions, lease/token lifecycle, worker-crash recovery, process-tree teardown, staging conformance tests, Supabase migration order, and controlled rollout.

This checklist is a deployment plan only. It does not indicate that a provisioner exists or that any checklist item has passed against a live runtime.


## Execution checkpoint 16 — source pin and collaboration foundation

**Status:** IN PROGRESS — NOT A COMPLETION CERTIFICATE  
**Date:** 2026-11-21  
**Base before this checkpoint:** 0a026bb5ac589df155cae5fdea096492f303d293  
**Hermes upstream revision:** 2de9f51b8008a7d49a49221c184f2f11cbfc4af1

### Changes committed

- Added Hermes upstream as a Git submodule at `engines/hermes/upstream`, pinned to the exact immutable source commit. `.gitmodules` retains the existing OpenCode submodule and adds Hermes independently.
- Added `docs/architecture/HERMES_SOURCE_AND_CAPABILITY_INVENTORY.md` describing the upstream package inventory, native API routes, license/provenance, and per-capability integration boundary.
- Added `services/api/app/services/engine_collaboration.py` with strict immutable artifact references, cross-engine task contracts, metadata-only events, result envelopes, ownership checks, media-type allowlists, bounded depth/concurrency/runtime/input, and rejection of same-engine handoffs.
- Added unit tests in `services/api/tests/test_engine_collaboration.py`.
- Added additive migration `20261121190000_engine_collaboration_foundation.sql` for owner-scoped artifact metadata, handoff records, collaboration events, and project workspace writer locks. Client roles receive read-only owner-scoped access; writes are reserved for the service role.

### Important discovery: runtime provisioner is present but Hermes is not yet supported

The repository already contains `services/runtime-provisioner`. Its current Docker manager and HTTP API are OpenCode-specific:
- It accepts only `engine_id=opencode`.
- It uses one OpenCode image and OpenCode environment/port/tmpfs assumptions.
- Runtime rows and recovery responses are not yet profile-aware.
- Its gateway allowlist proxies OpenCode routes only.

Therefore, the earlier statement that no provisioner implementation exists was too broad. The accurate state is: a provisioner implementation exists for OpenCode, but Hermes task-profile provisioning and its API gateway are not yet implemented.

### Verification status

- No test command was executed by this checkpoint; CI must validate the new contract tests and migration syntax.
- The Git submodule pointer is committed; recursive checkout/build and upstream Docker image digest verification remain to be run.
- No Docker daemon, Hermes image, live model/provider, or live Supabase project was changed.
- The migration is committed but not applied to any database.
- Hermes remains disabled. The collaboration module defines and validates contracts but is not yet wired to a durable handoff API/worker scheduler; the migration supplies persistence primitives but not lifecycle RPCs.

### Remaining engineering gates

1. Extend the provisioner for a dedicated Hermes image/profile and native API gateway, retaining the OpenCode path unchanged.
2. Add Hermes API-server startup/readiness and secure per-runtime API key injection; use the upstream port 8642 and strict route allowlist.
3. Implement SULY-owned memory namespace and memory read/write policy; keep native sessions ephemeral and task-scoped.
4. Implement signed/hashed skill manifests, provenance review, installation lifecycle, and task-level enablement.
5. Implement tool permission mapping and MCP credential/server broker.
6. Implement durable handoff lifecycle RPCs and worker scheduling, including approval, parent-child cancellation, retries, budgets, and artifact publication.
7. Add unified provider gateway and SULY-owned cron translation.
8. Run API/provisioner tests, migration checks, Docker image build, container security tests, and cross-tenant end-to-end tests on staging.

**Overall status remains IN PROGRESS. No claim of full Hermes integration or production readiness is made.**


---

## Execution checkpoint 17 — Hermes native provisioner path, engine separation, and collaboration contracts

**Checkpoint date:** 2026-11-21  
**Branch:** `main`  
**Hermes upstream revision:** `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`  
**Status:** IMPLEMENTATION CONTINUES — NOT A PRODUCTION COMPLETION CERTIFICATE

### Corrections to earlier checkpoints

The statements in checkpoints 13–16 that the repository had no provisioner implementation, or that its provisioner supported OpenCode only, are historical and have been superseded by the current `main` implementation. The repository now contains a multi-engine provisioner path for both OpenCode and Hermes. This does **not** mean a live provisioner host or production runtime has been deployed or verified.

### Original Hermes source

- Added `engines/hermes/upstream` as an independent Git submodule pinned to the exact upstream commit above.
- Preserved the existing OpenCode submodule entry in `.gitmodules`; Hermes and OpenCode source trees remain separate.
- The upstream Dockerfile and license remain upstream-owned; SULY does not copy Hermes into the FastAPI process or fork it into an unverified reimplementation.
- The upstream API server is enabled only inside a task-scoped Hermes container with a per-runtime key. Its exposed route surface is constrained by the SULY provisioner gateway.

### Hermes task runtime path now present in code

The current `services/runtime-provisioner` implementation includes:

- Separate digest-pinned image configuration for `OPENCODE_RUNTIME_IMAGE` and `HERMES_RUNTIME_IMAGE`.
- Separate manager identities, containers, private internal Docker networks, task-attempt directories, process trees, runtime tokens, and expiry cleanup.
- Exact Hermes profile enforcement: `suly-hermes-task-v1`.
- Hermes API server on container port 8642, published only on host loopback, with an HMAC-derived per-runtime credential.
- A separate task-local `/opt/data` and `/workspace`; no shared writable Hermes home across attempts.
- Restrictive task config: no native memory writes, no user-profile memory, no upstream orchestration/delegation, and no terminal/browser/computer-use/file/web/MCP/skills toolsets granted by default.
- An engine-specific route allowlist for Runs API admission/status/events/stop/steer/one-time approval, health/capabilities/models, and read-only skill/toolset metadata.
- Internal Docker networks remain egress-disabled. There is still no task-aware outbound model-provider proxy; do not turn on direct egress as a workaround.

### Additional separation fixes in this checkpoint

- The OpenCode convenience `/execute` route now rejects Hermes runtimes. Hermes tasks must use the native Runs API so upstream run identity, approvals, events, cancellation, and SULY leases remain correlated.
- The OpenCode workspace-results exporter now rejects Hermes runtimes. Hermes output is handled by the Hermes/SULY task-result path rather than being treated as an OpenCode changeset.
- Result retrieval selects the manager for the recorded engine identity rather than silently defaulting to OpenCode.
- Added regression tests for these cross-engine rejection boundaries.

### Collaboration layer

- Added strict typed collaboration contracts for cross-engine task handoffs, immutable owner-scoped artifact references, metadata-only lifecycle events, bounded result envelopes, approved media types, depth/concurrency/runtime/input budgets, and same-engine handoff rejection.
- Added unit tests for owner mismatch, duplicate artifacts, malformed events, unsupported media types, budget bounds, and expected-engine result validation.
- The repository also contains the durable collaboration handoff API/router and additive SQL lifecycle migrations. These remain **code-level integration** until the migrations are applied and RPC/RLS behavior is verified against a staging database.
- A handoff is not allowed to share a live process, session, memory namespace, writable directory, secret, or provider credential between engines. Parent approval and SULY task creation remain the intended handoff boundary.

### CI evidence

For commit `361f3175606949561beccf1344731b560e4f2f7d`:

- Runtime Provisioner CI run `44900390070`: **47 passed, 5 warnings**.
- Repository baseline checks run `44900390092`: **passed**.
- Platform CI run `44900390076`: pending at report preparation.
- OpenCode upstream verification run `44900390067`: pending at report preparation.

The provisioner tests use fake Docker clients and API test doubles. They do not prove a real Docker host, kernel isolation, host firewall, TLS ingress, upstream Hermes image startup, live model access, or successful end-to-end AI task execution.

### Live Supabase state checked read-only

The connected Supabase project `razvryvazmqvvqkzetuo` is `ACTIVE_HEALTHY` on PostgreSQL 17.11. Its migration history currently ends at `20261120003706`. The engine-run and collaboration migrations committed in this repository after that version are **not applied** to the live database. The currently visible public tables do not yet include the engine-run or collaboration tables.

No remote migration was applied in this checkpoint. This is intentional: the pending migration chain must first be reconciled and validated as a whole against the live schema; applying only a late migration would be unsafe.

### Remaining gates — still mandatory

1. Validate the complete ordered Supabase migration chain against a disposable/staging database, including RLS, grants, owner constraints, RPC privileges, and migration ordering. Then obtain explicit deployment approval before touching production.
2. Build the Hermes image from the pinned submodule, record its immutable image digest, and run it on a dedicated non-root worker host with real Docker.
3. Verify task-level kernel/container isolation, process-tree teardown, resource limits, host/metadata isolation, expiry recovery, and cross-tenant non-interference.
4. Implement a task-aware model/provider egress gateway. Until then, the current no-egress profile cannot make real provider-backed model calls.
5. Implement SULY-owned persistent memory, native session mapping, reviewed skill installation/execution, tool permission grants, MCP credential brokering, and bounded child-task delegation as separate gated components. Their upstream existence is not proof that SULY has integrated them.
6. Finish provider-independent usage/budget accounting and collaboration result/artifact verification.
7. Run the final API/client/provisioner CI on the latest commit, then staging runtime and end-to-end tests.

**Readiness after checkpoint 17:** source provenance and task-runtime code are materially advanced; OpenCode/Hermes execution shortcuts are separated; collaboration contracts and durable handoff code exist. Hermes remains **not safe to enable in production** until the database, provider egress, real container isolation, and runtime conformance gates above pass. Overall integration remains **IN PROGRESS**.
