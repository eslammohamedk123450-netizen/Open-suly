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

The current bridge uses Hermes' native `/v1/runs` admission and status endpoints, a stable per-attempt `Idempotency-Key`, a lease-guarded persisted upstream run ID, and the upstream stop endpoint for cooperative cancellation. Status polling is bounded; SSE event forwarding is a later enhancement. Upstream errors are redacted. The isolation flag is only an operator assertion, not a sandbox implementation. The bridge does not pass SULY identity claims, approval scopes, database credentials, or provider secrets to Hermes.

## Verification boundary

The bridge unit tests use a mocked HTTP endpoint. No live Hermes container, provider, model inference, tool execution, or end-to-end durable task has been verified yet. SULY's worker lease/checkpoint remains the only authority for task completion.
