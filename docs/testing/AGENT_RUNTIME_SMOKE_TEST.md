# SULY Agent Runtime — Local Smoke Test

This guide brings up the authenticated API and durable task worker for a real end-to-end test of the SULY task queue. The first test uses the deterministic `text.analyze` operation and does not need an AI provider. Hermes inference remains disabled until its isolated runtime sandbox and model provider have been reviewed and configured.

## 1. Required server-only environment

Create an untracked `.env` file in the repository root. Never place these values in `apps/client/.env`, Expo public variables, or source control.

```dotenv
SUPABASE_URL=https://razvryvazmqvvqkzetuo.supabase.co
SUPABASE_SECRET_KEY=YOUR_SERVER_ONLY_SUPABASE_SECRET_KEY
SUPABASE_PUBLISHABLE_KEY=
SULY_WORKER_ID=suly-local-worker
WORKER_LEASE_SECONDS=90
WORKER_POLL_INTERVAL_SECONDS=2
```

Use the Supabase project's current secret key. Do not use a service-role or secret key in the mobile/web client. Keep `HERMES_AGENT_ENABLED=false`.

## 2. Start the API and worker

From the repository root on a machine with Docker Compose:

```sh
docker compose --env-file .env -f deploy/docker-compose.test.yml up --build -d
docker compose --env-file .env -f deploy/docker-compose.test.yml ps
curl http://127.0.0.1:8000/health
```

The API health endpoint confirms process liveness only. It does not claim Supabase or Hermes readiness. Check startup and worker logs:

```sh
docker compose --env-file .env -f deploy/docker-compose.test.yml logs --tail=100 api worker
```

For an Android phone to reach an API running on the same Wi-Fi network, start Compose with `SULY_API_BIND=0.0.0.0` and set the client's API URL to the computer's LAN IP. Only do this on a trusted private network and allow the port through the local firewall.

## 3. Point the Expo client at the API

Set `EXPO_PUBLIC_API_BASE_URL` in the local `apps/client/.env` file to the reachable API origin, for example `http://192.168.1.20:8000` for a trusted local Wi-Fi test. This is a public API origin, not a secret. Rebuild/restart Expo after changing environment variables.

The client still uses the Supabase publishable key and authenticated Supabase session. The server secret stays only in the API/worker environment.

## 4. Run the first real task

1. Start the SULY client and sign in with a test account.
2. Open **وضع الوكيل** from the home composer.
3. Choose **اختبار محرك المهام**.
4. Paste a short Arabic or English paragraph and submit.
5. Confirm the task moves through the queue and reaches **اكتملت**.
6. Inspect the step output for `character_count`, `word_count`, `line_count`, and the bounded preview.
7. Submit another task, then cancel it while it is pending/running to check cancellation behavior.

This verifies the mobile client → authenticated API → Supabase durable task/step queue → worker allow-list → persisted output path. It is a real worker integration test, but it is not a live Hermes model-inference test.

## 5. Hermes-specific gate

The Hermes button is approval-gated in the client and server. A successful user approval only grants the SULY scope `agent.hermes.run`; it does not enable Hermes by itself.

Do not set `HERMES_AGENT_ENABLED=true` or enable the Hermes API server until all of the following are true:

- The Hermes container is pinned to the reviewed upstream commit.
- The Hermes API runs on a private network with no public host port.
- A dedicated non-root sandbox is enforced for terminal/filesystem tools, with bounded CPU, memory, processes, disk, workspace mounts, and egress.
- No Docker socket, host mounts, Supabase credentials, or SULY admin secrets are passed to Hermes.
- The Hermes tool policy is allow-listed and reviewed; the API key is stored only in a secret manager.
- A model provider and its budget/rate limits are deliberately configured.

The current Compose Hermes profile deliberately keeps `API_SERVER_ENABLED=false`. This is a security gate, not a missing UI switch.

## 6. Stop the test stack

```sh
docker compose --env-file .env -f deploy/docker-compose.test.yml down
```

Do not add `--volumes` unless you intentionally want to remove local container volumes.
