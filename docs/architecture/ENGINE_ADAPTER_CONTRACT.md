# SULY engine adapter contract

**Status:** interface foundation only; no external engine is enabled by this document.

## Responsibilities

- **SULY control plane:** authentication, tenant ownership, task/DAG state, leases, approvals, quotas, audit, usage, and billing.
- **Tool Registry:** operation allow-list, input schema bounds, approval scope checks, and handler dispatch.
- **Engine Registry:** engine metadata, supported capabilities, enabled state, and adapter discovery.
- **Engine Adapter:** narrow transport boundary to one isolated engine runtime.
- **Engine runtime:** executes only the task-scoped request it receives; it is not an authority for SULY identity or permissions.

The Engine Registry is not a replacement for the Tool Registry. A task must pass SULY's existing authorization and approval checks before any future adapter invocation.

## Contract data

The first implementation lives in:
- `services/api/app/services/engine_contract.py`
- `services/api/app/services/engine_registry.py`

An `EngineRequest` contains only a SULY task identifier, requested capability, bounded task input, and timeout. It deliberately excludes user identity claims, approval grants, Supabase clients, and provider credentials.

An `EngineResult` identifies the responding engine and returns structured output. All engine output is untrusted and must be size-limited, validated, audited, and treated as data—not executable instructions—by the caller.

An `EngineDefinition` declares:
- stable engine ID and display name;
- capability strings;
- disabled-by-default enablement;
- approval requirement metadata;
- input/output/timeout ceilings;
- optional adapter implementation.

## Current behavior and limits

- Registry operations are in-memory metadata registration and capability lookup only.
- No adapter is invoked by the worker.
- No automatic engine selection, failover, parallel delegation, or live health probing exists yet.
- Registering an engine does not enable it; `enabled=False` is the default.
- A capability lookup returns enabled matches only.
- The existing worker allow-list remains authoritative for executable operations.

## Required gates before live adapter execution

1. Resolve the selected engine from trusted SULY policy, never from a user-supplied arbitrary URL or module path.
2. Verify task ownership, approval scope, quota, and lease immediately before invocation.
3. Serialize only the minimal task payload; never forward secrets, auth tokens, database clients, or ambient host access.
4. Invoke a pinned runtime through a fixed adapter transport with strict connect/read/overall timeouts.
5. Enforce request and response byte limits, schema validation, and redaction.
6. Treat output as untrusted; store it as task output only after validation and lease/cancellation checks.
7. Audit engine ID, pinned version, task ID, timing, bounded status, and usage without logging secrets or full sensitive prompts.
8. Support timeout, cancellation, lease loss, retry policy, and process cleanup.
9. Keep the engine disabled until its exact source revision, licenses, dependencies, sandbox, and contract tests are reviewed.

## Next implementation steps

1. Add contract tests for registry validation and default-disabled behavior.
2. Add a deterministic in-process mock adapter for tests only.
3. Integrate registry lookup behind the existing worker dispatch boundary without changing approval semantics.
4. Add Hermes adapter lifecycle support (run ID, events, cancellation) after sandbox review.
5. Add one specialist adapter at a time, beginning with the coding/browser candidate selected by benchmark and license review.
