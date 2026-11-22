# SULY Agent Runtime Model

## Product contract

SULY owns the user-facing product, identity, authorization, task graph, memory,
approvals, artifacts, billing, audit trail, and final delivery. Engines are
specialist agents embedded as pinned upstream source/runtime components; they
are not user-facing hosted AI services.

## Agent roles

- **Hermes** is the intended primary orchestration agent. The current worker
  invokes the pinned native Hermes runtime and supplies approved skills and
  SULY-scoped context. Native Hermes subagent/delegation toolsets are currently
  disabled in the runtime profile; the SULY-controlled delegation bridge is a
  remaining implementation requirement before Hermes can dispatch specialist
  agents end-to-end.
- **OpenCode** is the coding specialist. It receives bounded coding tasks,
  works on a task-scoped project snapshot, and returns a reviewable change set.
- Additional agents are registered by immutable engine manifest, declared
  capabilities, reviewed adapter, and runtime profile. Catalog metadata alone
  never enables an engine.

## Runtime isolation

Every engine attempt is keyed by `(user_id, project_id, task_id, engine_run_id)`.
A runtime lease must bind the exact task, attempt, and engine. A new attempt
gets a fresh runtime; runtimes, credentials, writable workspaces, and upstream
sessions are never shared across users or tasks. Memory is not implicitly
shared between agents: SULY passes only bounded, owner-authorized context.

The runtime image contains the pinned upstream engine code and its own
dependencies. The SULY API talks only to that attempt's lease-bound runtime
gateway. This is **not** a connection to a hosted Hermes/OpenCode SaaS service.
The runtime provisioner is infrastructure that creates and destroys isolated
containers; it is not the agent's brain.

## Task lifecycle

1. SULY authenticates the user and creates the durable task/step lease.
2. The planner resolves task capabilities and approved context.
3. The dispatcher selects an enabled engine adapter by capability.
4. The provisioner creates a fresh runtime from the engine's reviewed profile.
5. The adapter executes with bounded input, timeout, output, and tool grants.
6. Results and artifact references are validated and persisted under the same
   task lease. Cross-agent handoffs require an explicit SULY approval.
7. Coding changes remain review-first; applying a change set is a separate,
   authorized action followed by a fresh verification/review pass.
8. Cancellation, timeout, lease loss, or worker restart triggers stop/recovery.
9. The runtime is released and its credentials revoked before the attempt is
   marked terminal. If cleanup cannot be confirmed, the run remains pending
   for reconciliation rather than being reported as cleanly completed.

## Current implementation boundary

The repository contains pinned upstream Hermes and OpenCode submodules and
image-build definitions. Hermes and OpenCode are provisioned as separate,
digest-pinned task containers; they are not embedded as long-lived processes in
the API worker. The task-scoped runtime model is implemented, but the full
Hermes-to-SULY delegation bridge (native delegation tool interception, durable
child-task creation, approval, result return, and parent resumption) is not yet
closed. Do not describe Hermes as a fully operational multi-agent orchestrator
until those paths and their integration tests are complete.

## External acceptance test boundary

Unit, contract, simulated-runtime, migration-contract, and CI tests belong to
the code-completion phase. Provisioner deployment, actual container startup,
upstream engine execution, hosted database migration, and production cleanup
verification belong to the later external acceptance test requested by the
product owner. Passing CI does not claim those external operations succeeded.
