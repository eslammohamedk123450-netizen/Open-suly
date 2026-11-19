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

The client may contain only public configuration. Never put provider credentials or Supabase secret/service-role keys in Expo public variables.

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

The connected project has been reset for the standalone SULY product. The first application migration is the identity foundation. Read [the clean-slate record](../operations/supabase-clean-slate.md) before making hosted database changes.

For local development:

```bash
supabase start
supabase migration list
```

For deliberate remote inspection:

```bash
supabase link --project-ref razvryvazmqvvqkzetuo
supabase migration list --remote
```

Do not import old migration files or execute old SQL. New schema changes must be committed as forward migrations. Never run destructive hosted reset operations as a routine development step.

## Verification

```bash
npm run typecheck
npm run web
```

For the API:

```bash
python -m compileall services/api/app
pytest -q
```

A successful liveness response does not prove Supabase connectivity. Database readiness must be verified separately when credentials and infrastructure are configured.
