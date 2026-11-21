# Hermes Runtime Provisioner — Staging and Activation Checklist

This checklist is a deployment gate for SULY's task-scoped Hermes runtime integration. It is intentionally separate from the API code: SULY does not include a Docker/containerd provisioner implementation in this repository.

## 1. Required infrastructure

- [ ] Dedicated Linux host or isolated runtime platform controlled by the operator.
- [ ] Container runtime socket is available only to the provisioner control plane; it is never mounted into Hermes containers.
- [ ] Provisioner is reachable from SULY API/worker over HTTPS with a valid certificate.
- [ ] The provisioner API is not publicly unauthenticated; use a high-entropy server-only bearer token.
- [ ] Exact provisioner origin is configured in `RUNTIME_PROVISIONER_ALLOWED_ORIGINS`.
- [ ] Task runtime gateway routes only to the runtime ID in the authenticated lease.
- [ ] Runtime containers have no shared writable filesystem or process namespace.
- [ ] Resource, PID, storage, wall-time, and concurrent-runtime quotas are enforced by the provider.

## 2. Mandatory Hermes profile: `suly-hermes-task-v1`

The provider must reject Hermes acquisition unless this profile is selected and must echo the exact profile in every acquired/recovered lease.

- [ ] One fresh whole-process runtime per task attempt.
- [ ] No host filesystem mounts, Docker socket, host PID namespace, or privileged container mode.
- [ ] Read/write access limited to the bounded task workspace snapshot.
- [ ] `.git`, `node_modules`, `.env*`, `secrets/`, and reserved paths never materialized.
- [ ] Terminal, browser, arbitrary MCP, package-install, and other privileged toolsets disabled by default.
- [ ] Network egress denied by default except the configured model gateway and explicitly reviewed destinations.
- [ ] Model/provider credentials are scoped to the runtime and never written to SULY task output or event metadata.
- [ ] Lease tokens are short-lived, runtime-specific, revocable, and never stored in Supabase.
- [ ] Recover rotates credentials without changing task/run/runtime/profile identity.
- [ ] Release revokes credentials and confirms complete process-tree teardown.
- [ ] Release is idempotent, including the case where the runtime is already absent.
- [ ] TTL cleanup runs independently of SULY worker health.

## 3. Provisioner conformance tests

Do not enable Hermes until all tests pass against the real staging provider.

- [ ] Two concurrent tasks receive different runtime IDs and cannot see each other's files.
- [ ] A token from runtime A cannot access runtime B or any other gateway route.
- [ ] Wrong task ID, engine-run ID, engine ID, runtime ID, or runtime profile is rejected.
- [ ] Missing or incorrect `suly-hermes-task-v1` profile is rejected by SULY.
- [ ] A runtime cannot reach the host, cloud metadata endpoints, Docker socket, Supabase service-role API, or arbitrary public destinations.
- [ ] Privileged toolsets remain disabled under the default profile.
- [ ] Expired/revoked tokens stop working immediately.
- [ ] Worker crash followed by recover and release removes the original process tree.
- [ ] Failed release remains `stop_pending` and is retried by the SULY reconciler.
- [ ] Runtime output and SSE events stay within SULY's response/event size limits.
- [ ] Runtime CPU, memory, PID, storage, and wall-time limits are actually enforced.

## 4. Supabase staging migration gate

Apply and verify the additive migrations in order before enabling the new code paths:

1. `20261121130000_engine_run_runtime_identity.sql`
2. `20261121140000_engine_runtime_stop_recovery.sql`
3. `20261121150000_engine_run_subagent_metadata.sql`
4. `20261121170000_task_conversation_context.sql`

Then verify:
- [ ] Runtime identity RPC accepts only the active task-step lease.
- [ ] Stop claim RPC returns runtime ID and task ID for Hermes cleanup.
- [ ] Missing-identity diagnostic RPC executes as `service_role`.
- [ ] Subagent metadata constraints reject content-bearing/unbounded metadata.
- [ ] Conversation foreign key enforces owner match and clears only the link when a conversation is deleted.
- [ ] RLS prevents cross-user reads and writes.

## 5. SULY rollout

- [ ] Keep `HERMES_AGENT_ENABLED=false` while provisioning and migration tests are incomplete.
- [ ] Configure the same provisioner URL/token/origin allow-list in API and worker environments.
- [ ] Enable `ENGINE_RECONCILER_ENABLED` only after the provider's recover/release contract is verified.
- [ ] Run one internal staging task with no privileged toolsets.
- [ ] Verify task completion is recorded only after confirmed runtime release.
- [ ] Verify a forced worker termination leaves a recoverable `stop_pending` run and the reconciler cleans it.
- [ ] Enable Hermes for a restricted internal user group before general availability.
- [ ] Keep the kill switch available and monitor provisioner failures, release retries, and runtime TTL cleanup.

## 6. Explicit non-goals of this checklist

Passing this checklist does not automatically implement persistent Hermes sessions, long-term memory, skill source/install/update management, MCP credential brokering, SULY-owned child-task budgets, or unified model-provider routing. Those are separate integration phases.
