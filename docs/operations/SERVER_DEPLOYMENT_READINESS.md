# SULY deployment readiness and acceptance boundary

This document prepares the application for a controlled server deployment. It does
not claim that external services, production credentials, database migrations,
or live engine execution have already been configured or tested.

## Deployment topology

1. **Public API**: FastAPI container, non-root, no Docker socket, no engine execution.
2. **Durable worker**: separate process/container using the same API image. It polls
   SULY's durable task queue and must not receive Docker socket access.
3. **Runtime Provisioner**: separate control-plane service on a dedicated VM/host
   with its own Docker daemon. It is the only component allowed to manage task
   containers. Never mount its Docker socket into API, worker, client, or task
   containers.
4. **Supabase**: managed PostgreSQL/Auth/Storage. The application does not bundle
   PostgreSQL in its application image.

## Build and run API + worker

Requirements: Docker Engine and Docker Compose v2 on a Linux host.

```sh
cp .env.example .env
# Edit .env on the server. Set Supabase URL, publishable key and server-only
# secret key. Keep all secret values out of Git and client build variables.
docker compose --env-file .env -f deploy/docker-compose.server.yml build
docker compose --env-file .env -f deploy/docker-compose.server.yml up -d api
docker compose --env-file .env -f deploy/docker-compose.server.yml ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

The compose file publishes API only on loopback by default. Put a TLS-terminating
reverse proxy/load balancer in front of it; do not expose the container port
directly to the public Internet. Configure ingress body-size, request timeout,
rate limits, DDoS protection, and trusted proxy headers there.

Start the durable worker only after database migrations and staging acceptance
checks have passed:

```sh
docker compose --env-file .env -f deploy/docker-compose.server.yml up -d worker
```

The worker is deliberately not started by the default command. The API container
has `WORKER_ENABLED=false`; the worker service explicitly sets it to true.

## Runtime Provisioner isolation

Deploy `services/runtime-provisioner` on a dedicated host/VM with a dedicated
Docker daemon and encrypted persistent storage. Follow
`services/runtime-provisioner/README.md` for image digests, host firewall,
loopback-only engine ports, TLS gateway, runtime lease persistence, and mandatory
default-deny network policy.

Do not co-locate the provisioner with the public API unless the host-level
security boundary has been independently designed and reviewed. Do not mount
`/var/run/docker.sock` into the API or worker. Do not enable task egress:
the current provisioner deliberately rejects it because a task-aware egress
gateway is not implemented and verified.

## Environment and activation order

- `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`: required
  for authenticated API operations and trusted server-side writes. The secret
  key is server-only.
- `WORKER_ENABLED`: false for API; true only in the worker service.
- `HERMES_AGENT_ENABLED` and `OPENCODE_ENABLED`: keep false until the provisioner
  is deployed, authenticated, TLS-reachable from the worker, and staging-tested.
- `RUNTIME_PROVISIONER_URL`, `RUNTIME_PROVISIONER_TOKEN`,
  `RUNTIME_PROVISIONER_ALLOWED_ORIGINS`: configure only on trusted server-side
  services. Allowed origins must be exact trusted HTTPS origins; never use
  wildcards.
- `AI_PROVIDER=disabled`: keep disabled until a provider is deliberately
  selected and its key is stored server-side.
- `AGENT_MEMORY_ENABLED` and `ENGINE_RECONCILER_ENABLED`: keep disabled until
  their migrations and recovery behavior are validated in staging.

Do not put server secrets in Expo `EXPO_PUBLIC_*` variables, browser storage,
mobile bundles, logs, task workspaces, or runtime images.

## Database migration gate

Before starting workers or enabling engines:

1. Provision a disposable/staging Supabase project.
2. Back up any existing staging data.
3. Apply every migration in `supabase/migrations` in lexical order using the
   Supabase CLI or the project's controlled migration pipeline.
4. Verify the migration history and inspect RLS policies, grants, indexes,
   triggers, and SECURITY DEFINER function search paths.
5. Run API integration tests against that staging project using non-production
   accounts for at least two different users.
6. Do not apply unreviewed migrations directly to production.

The static migration tests in CI are not evidence that PostgreSQL has executed
the migrations successfully.

## Acceptance sequence

- API health and readiness; invalid/missing Supabase credentials fail closed.
- Authentication, tenant ownership, RLS, Storage policies and rate limiting.
- Worker claim, lease renewal, retries, cancellation, crash recovery and cleanup.
- Hermes and OpenCode each in separate per-attempt runtimes.
- Cross-user and cross-project isolation tests.
- Approval enforcement, OpenCode review/apply/re-review, and audit records.
- Provisioner host firewall, TLS, Docker daemon isolation and network egress denial.
- Load, concurrency, resource quotas, log redaction, backup and restore.

Enable engine flags only after the corresponding acceptance checks pass. Keep
external execution disabled until then.

## Operational notes

- `/health` is a liveness endpoint only.
- `/ready` checks required Supabase configuration; it does not perform a live
  database query and is not proof of database availability.
- API rate limits are per process. Enforce global limits at the ingress.
- Render's current free web-service template is a lightweight API preview only:
  it sleeps when idle and does not deploy the durable worker or isolated runtime
  provisioner. It is not the recommended topology for live agent execution.
