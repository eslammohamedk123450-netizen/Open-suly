# Hermes Agent runtime for SULY

SULY pins the complete upstream Hermes Agent runtime as a remote Docker build context:

- Upstream: https://github.com/NousResearch/hermes-agent
- Pinned commit: `2de9f51b8008a7d49a49221c184f2f11cbfc4af1`
- License at the pinned upstream source: MIT; preserve upstream copyright and license notice.
- Upstream Dockerfile is used directly; SULY does not fork or flatten Hermes into the FastAPI environment.

## Safety defaults

- Compose profile: `agent-engines` (not started by the default compose profile).
- `API_SERVER_ENABLED` defaults to false.
- No host port is published.
- Persistent state is isolated in the `hermes-data` named volume.
- The service has no Supabase credentials or SULY admin secrets.
- The API server exposes Hermes' full agent toolset, including terminal execution. It is hard-disabled in this Compose file; do not change that setting until a dedicated sandbox/tool policy review is complete.
- If the API is enabled after that review, set a unique upstream `API_SERVER_KEY` through the deployment secret manager. Never commit it.
- The SULY HTTP bridge is disabled by default. The `hermes.agent.turn` task operation is registered behind persisted user approval, but cannot execute until the Hermes API, provider, database migrations, and per-task isolation are configured and verified.
- Hermes still requires a deliberately configured model provider. SULY has not selected or configured one.

## Build / start

From the repository root, with Docker Compose supporting remote Git build contexts:

```sh
docker compose -f engines/hermes/compose.yaml --profile agent-engines build
docker compose -f engines/hermes/compose.yaml --profile agent-engines up -d
```

The current configuration starts the Hermes gateway with its API server hard-disabled. This validates packaging/build only; it does not enable SULY-to-Hermes task execution or real model inference. Upstream describes Hermes as a single-tenant personal agent. A shared process is not an acceptable multi-tenant boundary; per-task or per-user OS/container isolation, resource limits, task-scoped storage, and default-deny egress must be implemented before enabling the API.

## SULY bridge settings

The FastAPI bridge uses these server-only environment variables:

- `HERMES_AGENT_ENABLED=false` (default; keep false until sandbox approval)
- `HERMES_AGENT_ISOLATION_CONFIRMED=false` (default; explicit operator attestation required by the bridge, but this flag does not itself create isolation)
- `HERMES_AGENT_BASE_URL` (internal service URL ending before `/v1`)
- `HERMES_AGENT_API_KEY` (same secret as the Hermes API server key; secret manager only)
- `HERMES_AGENT_MODEL=hermes-agent`
- `HERMES_AGENT_TIMEOUT_SECONDS=90`
- `HERMES_AGENT_MAX_OUTPUT_CHARS=12000`

The task worker now acquires a distinct runtime lease for each SULY engine-run attempt through the HTTPS runtime provisioner. The provisioner is a separate trusted service; the public API process has no Docker socket and does not launch containers itself.

The worker persists only the opaque runtime UUID in the SULY engine-run ledger. The short-lived runtime access token is never stored in Supabase. Hermes traffic is sent through the lease's exact runtime gateway path; approval detail, approval resolution, steering, and orphan cleanup recover a short-lived lease using the stored runtime/task/run identity. Outbound Hermes HTTP clients disable ambient proxy variables and redirects.
 When a task is linked to a SULY project, the worker also snapshots that owner's bounded project files (maximum 200 files / 5 MiB, with reserved paths and secret-like files excluded) and asks the provisioner to materialize them inside that task's fresh runtime. Project files are never mounted from the API host filesystem.

The bridge uses Hermes' native `/v1/runs` admission and status endpoints, a stable per-attempt `Idempotency-Key`, lease-guarded upstream run ID persistence, bounded status polling, metadata-only SSE progress, and cooperative cancellation. Subagent lifecycle events are reduced to an allow-listed set of opaque identifiers and counters; goals, summaries, prompts, tool arguments, reasoning, and output text are not persisted as event metadata.

### Required runtime provisioner settings

- `RUNTIME_PROVISIONER_URL` — HTTPS origin of the trusted provisioner.
- `RUNTIME_PROVISIONER_TOKEN` — server-only bearer credential for the provisioner.
- `RUNTIME_PROVISIONER_ALLOWED_ORIGINS` — exact HTTPS origins permitted for per-runtime gateway leases.
- `RUNTIME_PROVISIONER_TIMEOUT_SECONDS` — bounded provisioner request timeout.
- `ENGINE_RECONCILER_ENABLED` — opt-in orphaned-run/runtime cleanup worker.

For Hermes, the provisioner must also return the exact runtime profile `suly-hermes-task-v1`; SULY rejects a lease that does not attest this profile. The profile contract requires a unique whole-process runtime per task attempt; no shared Hermes process or host filesystem; terminal, browser, arbitrary MCP, package-install, and other privileged toolsets disabled unless a separately reviewed SULY grant explicitly enables them; network egress denied by default except the configured model gateway; bounded CPU, memory, PID count, storage, and wall time; and authenticated recover/release semantics that revoke credentials and tear down the complete process tree. A gateway lease must route only to the matching runtime. The profile string is an authenticated provider contract, not proof that the provider's OS-level enforcement has been deployed or tested.
 The exact SULY control-plane request/response and Hermes gateway routes are specified in [the runtime provisioner OpenAPI contract](../../docs/runtime-provisioner-openapi.yaml).
 Before activation, complete [the staging and activation checklist](../../docs/HERMES_RUNTIME_PROVISIONER_ACTIVATION_CHECKLIST.md).

`HERMES_AGENT_ISOLATION_CONFIRMED` remains an operator attestation gate; it is not proof of isolation. Keep `HERMES_AGENT_ENABLED=false` until the provisioner is deployed and its security controls are tested. Do not use the single-service Compose profile or its named volume as a multi-tenant runtime.

The bridge does not pass SULY identity claims, approval grants, database credentials, or Supabase service keys to Hermes. Toolset discovery is descriptive only; SULY approvals remain authoritative. The current integration does not yet provide SULY-owned skill installation/update, persistent memory, session mapping, MCP credential brokering, or separately budgeted child-task orchestration.

## Verification boundary

The bridge and lease lifecycle are covered by mocked API/provider tests and repository CI. No live Hermes container, provisioner, provider, model inference, tool execution, PostgreSQL migration application, cross-tenant isolation, or end-to-end durable task has been verified. SULY's worker lease/checkpoint remains the only authority for task completion.
