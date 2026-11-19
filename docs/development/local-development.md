# Local development

## Prerequisites

- Node.js 22.13 or newer and npm.
- Python 3.12 or newer.
- Supabase CLI for local database work.
- Android Studio / Android SDK for local Android builds, or an appropriate Expo development environment.

## Client

From the repository root:

```bash
npm install
npm run web
```

To start the Android development target:

```bash
npm run android
```

The client reads only the public API origin from `apps/client/.env`. Copy `apps/client/.env.example` to that path for local development. Never put provider credentials or Supabase service-role keys in Expo public variables.

## API

```bash
cd services/api
python -m venv .venv
# Activate the virtual environment for your operating system.
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health endpoint: `http://127.0.0.1:8000/health`.

## Supabase

Install the Supabase CLI, then run:

```bash
supabase start
supabase migration list
```

Database schema and RLS migrations are introduced in the database/security milestone. Do not create production tables or policies manually outside versioned migrations.

## Verification

```bash
npm run typecheck
npm run web
```

For the API, install `services/api/requirements.txt`, then run:

```bash
python -m compileall services/api/app
```

A successful liveness response does not prove Supabase connectivity. Database readiness must be verified separately when project credentials and local infrastructure are configured.


## Existing hosted Supabase project

The connected project is an existing populated database, not a blank database. Read [the verified baseline](../operations/supabase-existing-project-baseline.md) before running migrations.

For a deliberate remote inspection, link the CLI to the existing project ref supplied in the baseline:

```bash
supabase link --project-ref razvryvazmqvvqkzetuo
supabase migration list --remote
```

Supabase CLI v3 runs database commands against the local stack by default. A hosted change must explicitly target `--remote`, and unattended hosted changes require an explicit `--yes`. Never run `db reset` against the hosted project. Review SQL and confirm the migration history before any production schema change.
