# Hermes upstream capability inventory — SULY checkpoint 02

**Date:** 2026-11-21  
**Repository branch:** main  
**Observed repository tree:** f0c1abbb996091df00bfeb4874408f87c3927854  
**Upstream:** NousResearch/hermes-agent  
**Pinned revision:** 2de9f51b8008a7d49a49221c184f2f11cbfc4af1

## Source integration status

Hermes is included as its original upstream source through a pinned Git submodule and is built from its upstream Dockerfile in an independent task runtime. This preserves upstream source/provenance and is preferable to copying the entire source tree into SULY's FastAPI or frontend packages. A submodule checkout is **not** proof that every upstream capability is exposed to SULY.

## Upstream areas identified in pinned tree

- Core agent/CLI and configuration: `hermes_cli/`, `agent/`, configuration examples.
- Gateway and APIs: `gateway/`, `gateway/platforms/`, native Runs API, session/memory-session endpoints, cron-job API, room dispatch/grants.
- Tools and execution: `tools/`, toolset registration and execution, terminal/browser/computer-use/file/web/MCP/delegation and related tool modules.
- Skills: `skills/`, skill discovery, skill manager, install/update flows, skill authoring and policy.
- Providers: `providers/`, provider/model configuration and adapters.
- MCP: upstream MCP integration and server lifecycle/discovery modules.
- Scheduling: `cron/`, scheduler/job definitions, lifecycle, delivery, quotas, retry/cancellation.
- Desktop and companion applications: `apps/` (not assumed to be part of SULY's mobile client).
- Testing and evaluation: `tests/`, `evals/`, workflow and quality scripts.
- Packaging/deployment: upstream Dockerfile, scripts, installer/bootstrap and deployment material.

## What SULY currently supports (code presence, not runtime certification)

- **Source/runtime packaging:** original pinned Hermes source, separate Docker image/runtime profile.
- **Runs API:** SULY adapter supports run admission, bounded status polling, stop, steering, one-time approval, progress metadata; provisioner proxy allowlists run endpoints.
- **Isolation:** task-attempt runtime manager supports Hermes and OpenCode as separate containers, internal Docker network, resource limits, no direct egress, task-specific workspace/home and lease identity. This code still needs deployed host and runtime-security verification.
- **Capabilities catalog:** Hermes is currently registered with only `agent.general`; broader upstream features are not automatically selectable.
- **Collaboration:** owner-scoped approval-gated cross-engine handoff lifecycle, task budget controls, durable handoff/event tables, and typed contracts exist in code/migrations. Verify migrations are applied and child tasks are actually dispatched/observed end-to-end before declaring integrated.
- **Skills/toolsets:** provisioner exposes read-only catalog routes; no SULY-owned skill execution, installation, update, permission review, or source provenance flow is complete.
- **Memory/sessions:** SULY bounded conversation context is present; Hermes native memory/session capability is intentionally disabled/not yet bridged into owner/project-scoped SULY records.
- **MCP:** upstream source exists, but SULY credential broker, tenant-scoped server registration, approval, and isolated execution are not integrated.
- **Delegation/subagents:** upstream native delegation is disabled in the task profile. SULY-owned child-task budget/cancellation/parallel execution integration is incomplete.
- **Providers/model routing:** provider credentials and model selection are not safely provisioned end-to-end for Hermes yet.
- **Cron/gateway channels:** upstream source is present but not integrated into SULY's task/scheduling/notification system.
- **Desktop/apps:** upstream desktop/companion apps are not merged into SULY client; evaluate only if they serve an explicit SULY product requirement.

## Required next implementation gates

1. Finish source-level inventory by component, APIs, tools, configuration, dependencies, and licenses; create a capability-by-capability implementation plan.
2. Design SULY-owned provider credential/model routing and a runtime-only credential injection path; do not persist raw secrets in task inputs, events, artifacts, or workspace snapshots.
3. Implement approved skill read/execute workflows with immutable source, digest, tenant/project scope, review, allowlist, and task isolation.
4. Implement SULY memory/session mapping with owner/project/task scope, retention, delete/export, and explicit approval boundaries; do not share runtime homes between tasks.
5. Implement MCP server registry and credential broker, strict destination/transport policy, and sandboxed tool execution; egress remains disabled until a destination-allowlisting proxy is tested.
6. Implement SULY-owned child-task orchestration, task contracts, depth/parallel/runtime/token budgets, artifact-only handoff, cancellation, and durable event transitions.
7. Add integration tests for APIs, runtime creation/teardown, crash recovery, cross-owner rejection, handoff lifecycle, tool permissions, secrets, and egress; run staging security tests before enabling feature flags.
8. Update the main integration report with evidence and explicit status distinctions (implemented, code verified, integration tested, runtime tested, production tested).

## Evidence limits

This inventory was generated from the pinned upstream Git tree and the currently observed SULY repository code. It is an engineering checkpoint, not a completion statement. No live Hermes runtime, provider/model inference, upstream tool execution, staging deployment, or production verification is claimed.
