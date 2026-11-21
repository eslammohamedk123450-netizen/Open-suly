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

The principal remaining work is not to duplicate these foundations. It is to complete the missing runtime security boundary and the capability adapters (skills, memory, sessions, delegation/subagents, MCP, provider routing, and lifecycle reconciliation) without weakening SULY's control plane.

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
