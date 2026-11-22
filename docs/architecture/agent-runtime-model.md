# SULY Agent Runtime Model

## Product contract

SULY owns the user-facing product, identity, authorization, task graph, memory,
approvals, artifacts, billing, audit trail, and final delivery. Engines are
specialist agents embedded as pinned upstream source/runtime components; they
are not user-facing hosted AI services.

## Agent roles

- **Hermes** is the primary orchestration agent. The worker invokes the pinned
  native Hermes runtime and supplies approved skills and SULY-scoped context.
  Hermes may return a versioned `SULY_ORCHESTRATION_V1` proposal; it must not
  spawn native subagents. SULY validates and routes each proposal through
  AgentManager and the durable delegation outbox.
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
task-scoped containers; they are not embedded as long-lived processes in the
API worker.

Completed Hermes steps can atomically enqueue a strictly validated delegation
proposal into a server-only Supabase outbox. The outbox uses row leases,
bounded retries, parent-cancellation handling, and stable request idempotency.
AgentManager chooses only an enabled, registered specialist capability. SULY
then creates durable handoffs in `pending_approval`; the outbox does not start
the specialist runtime. The existing owner-approval RPC remains the only path
that creates an executable child task.

Parent cancellation now terminalizes outstanding collaboration handoffs, records
metadata-only cancellation events, and requests cancellation of already-approved
child tasks. Child task completion, failure, and cancellation are also reflected
as durable handoff terminal events; the actual child result remains in its
owner-scoped task-step checkpoint rather than being copied into event metadata.

The durable parent/child continuation lifecycle is now implemented in
migration `20261122070000_durable_parent_child_continuation.sql`. A parent moves
to `waiting_children` as soon as a delegation outbox row or handoff is created.
The approval RPC accepts additional sibling approvals while the parent is in
that state. Terminal handoff and outbox transitions re-check the complete
barrier; once all sibling handoffs and deliveries are terminal, SULY inserts a
single idempotent continuation step keyed by the original parent engine run.
The parent remains `waiting_children` until `claim_task_step` rechecks that exact
run's outbox and handoff barrier, then atomically claims the continuation and
moves the parent to `running`. The continuation contains bounded owner-scoped
child step outputs, review decisions, and handoff statuses as explicitly
untrusted context. Hermes and OpenCode continuation operations are supported
by their existing task adapters. Parent cancellation
prevents resumption, and the existing cancellation cascade requests child
cancellation. The child terminal synchronizer is reduced to one trigger to
avoid duplicate writers.

The continuation step is durable database state, not worker memory: a worker
restart does not lose the resume request. Its unique task/step key makes the
insert idempotent, and the worker claim transaction rechecks pending outbox and
handoff rows to avoid resuming while sibling work is still active. Parent
cancellation remains available while waiting and prevents continuation claims. Static
migration invariants are covered in CI. Database execution, concurrent
transaction behavior, hosted runtime startup, and real engine acceptance
remain part of the separately deferred non-production/external acceptance
test; CI is not represented as proof of those external behaviors.


OpenCode change sets now have a complete owner-gated apply/re-review path.
Applying an initial change set atomically queues one durable post-apply review
step against the actual updated project snapshot. The review prompt is
read-only; any proposed fixes are returned as a fresh change set and still
require owner approval. A review step is marked with its source change-set ID,
so applying its own result cannot recursively enqueue infinite review steps.
For OpenCode child tasks, the collaboration handoff remains running while a
change set is awaiting owner decision and through the post-apply review; the
parent is resumed only after the final review change set is applied, rejected,
or becomes stale. The decision is persisted in the handoff and included in the
parent's continuation context.

## External acceptance test boundary

Unit, contract, simulated-runtime, migration-contract, and CI tests belong to
the code-completion phase. Provisioner deployment, actual container startup,
upstream engine execution, hosted database migration, and production cleanup
verification belong to the later external acceptance test requested by the
product owner. Passing CI does not claim those external operations succeeded.
