# Hermes Agent runtime for SULY

SULY pins the complete upstream Hermes Agent runtime as a remote Docker build context:

- Upstream: https://github.com/NousResearch/hermes-agent
- Pinned commit: `9f47677483d1b4de4d1a88d37b3b7ca18b18b215`
- License at the pinned upstream source: MIT; preserve upstream copyright and license notice.
- Upstream Dockerfile is used directly; SULY does not fork or flatten Hermes into the FastAPI environment.

## Safety defaults

- Compose profile: `agent-engines` (not started by the default compose profile).
- `API_SERVER_ENABLED` defaults to false.
- No host port is published.
- Persistent state is isolated in the `hermes-data` named volume.
- The service has no Supabase credentials or SULY admin secrets.
- The API server exposes Hermes' full agent toolset, including terminal execution. Do not set `HERMES_API_SERVER_ENABLED=true` until a dedicated sandbox/tool policy review is complete.
- If the API is enabled after that review, set a unique `HERMES_API_SERVER_KEY` through the deployment secret manager. Never commit it.
- The SULY HTTP bridge is disabled by default and is not registered as an executable task tool yet.
- Hermes still requires a deliberately configured model provider. SULY has not selected or configured one.

## Build / start

From the repository root, with Docker Compose supporting remote Git build contexts:

```sh
docker compose -f engines/hermes/compose.yaml --profile agent-engines build
docker compose -f engines/hermes/compose.yaml --profile agent-engines up -d
```

The current default starts the isolated gateway process with the Hermes API disabled. This validates packaging/build only; it does not enable SULY-to-Hermes task execution or real model inference.

## SULY bridge settings

The FastAPI bridge uses these server-only environment variables:

- `HERMES_AGENT_ENABLED=false` (default; keep false until sandbox approval)
- `HERMES_AGENT_BASE_URL` (internal service URL ending before `/v1`)
- `HERMES_AGENT_API_KEY` (same secret as the Hermes API server key; secret manager only)
- `HERMES_AGENT_MODEL=hermes-agent`
- `HERMES_AGENT_TIMEOUT_SECONDS=90`
- `HERMES_AGENT_MAX_OUTPUT_CHARS=12000`

The bridge sends only a bounded user prompt, uses a fixed non-streaming Chat Completions request, redacts upstream errors, and bounds the response. It does not pass SULY identity claims, approval scopes, database credentials, or provider secrets to Hermes.

## Verification boundary

The bridge unit tests use a mocked HTTP endpoint. No live Hermes container, provider, model inference, tool execution, or end-to-end durable task has been verified yet. SULY's worker lease/checkpoint remains the only authority for task completion.
