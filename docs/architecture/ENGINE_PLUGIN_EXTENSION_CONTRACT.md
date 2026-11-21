# SULY Engine Plugin Extension Contract

Status: architecture contract; additional engines remain disabled until their adapter, runtime image, permissions, lifecycle handlers, and database handoff policy are implemented and verified.

## Control-plane ownership

SULY remains authoritative for user identity, task/step leases, engine-run IDs, approvals, quotas, usage accounting, audit events, project ownership, artifact references, and final result acceptance. An engine is an isolated execution backend, not an identity or policy authority.

## Registering an additional engine

1. Add an `EngineManifest` to the reviewed extension manifest set:
   - stable lowercase `engine_id`;
   - canonical HTTPS upstream repository;
   - immutable 40-character source commit;
   - verified SPDX/license identifier;
   - purpose/role;
   - explicit capability identifiers.
2. Implement an `EngineAdapter` that accepts only `EngineRequest` and returns bounded `EngineResult`. Do not include user identity claims, approval grants, provider secrets, Supabase clients, or runtime credentials in either payload.
3. Supply an explicit server-side runtime override. Metadata-only registration leaves the engine disabled. Enabling requires a concrete adapter.
4. Implement a dedicated runtime profile and provisioner driver: digest-pinned image, non-root identity, isolated task workspace and home, resource limits, no Docker socket, no direct egress, per-runtime credentials, health/readiness contract, authenticated route allowlist, recovery, cancellation, teardown, and expiry reaper.
5. Add a tool/capability policy mapping. Every privileged operation must be independently allow-listed and bound to persisted user approval. An upstream tool catalog is descriptive only and never grants permission.
6. Add durable engine-run identity and event mapping, idempotent admission, remote stop/reconciliation, lease-loss recovery, and orphan cleanup.
7. Add collaboration target/source mapping and database constraints/RPC support. A new engine manifest alone does **not** make it eligible for cross-engine handoff.
8. Add owner-scoped result/artifact persistence and review/apply semantics. Results are untrusted; artifacts cross engine boundaries only as owner-scoped immutable references.
9. Author isolation, cancellation, crash-recovery, cross-tenant, permission, result-validation, and teardown tests. Keep the runtime disabled until CI and deployment verification pass.

## Current boundary

The Python engine catalog now accepts additional reviewed immutable manifests and explicit adapter overrides. The built-in Hermes Agent, OpenCode, and Browser Use metadata remain disabled unless explicitly overridden. This is an extension point in the control-plane registry, **not** a claim that arbitrary new runtimes can already be provisioned or used for collaboration.

The current Docker runtime provisioner supports only the two implemented runtime drivers: `hermes-agent` and `opencode`. The collaboration SQL RPC currently accepts only the Hermes/OpenCode pair and their explicitly enumerated capabilities. A future engine must not be advertised as executable until those runtime and SQL integration layers are extended for it.

## Hermes skills, memory, and tools

- SULY's explicit `agent_memories` table is the memory authority. The worker injects a bounded, read-only, owner-scoped subset as untrusted context when memory is enabled. Engines do not write this table directly.
- Native Hermes memory and delegation remain disabled in the per-task profile to prevent a second persistence/identity authority.
- Hermes skills and toolsets are not yet an enabled SULY capability bridge. The provisioner exposes only the read-only skill/toolset discovery routes; discovery must not be confused with reviewed skill activation or tool permission.
- Before enabling skills, add a pinned skill manifest with source revision, license, content digest, allowed capabilities, and review status; reject unreviewed or changed content. Skills must never grant themselves tools or secrets.
- Before enabling native tool execution, route each tool through SULY's capability registry, persisted approval scopes, audit/usage accounting, bounded outputs, and cancellation-aware execution. Keep terminal, browser, MCP, filesystem mutation, and delegation disabled until their separate adapters and sandboxes are verified.

## OpenCode result lifecycle

OpenCode runs in a task-scoped runtime. SULY persists the session/run mapping and sanitized events, collects a bounded change set against a captured workspace revision, and requires an explicit owner decision. Apply is a transactional compare-and-swap; reject/apply releases the runtime. Failed execution attempts release immediately. A runtime that cannot be confirmed stopped remains pending for the provisioner's expiry reaper and durable reconciliation; a successful API response alone is not proof that every process has exited.
