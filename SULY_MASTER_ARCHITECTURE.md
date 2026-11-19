# SULY — Fresh Product Architecture

**Status:** New product foundation  
**Product:** SULY — More Than AI. Your Intelligent Partner.

## 1. Product boundary

SULY is a standalone AI application designed and implemented from a clean slate. Previous applications and their internal systems are retired and must not be treated as a source of business logic or architecture.

The only reusable elements are SULY's name, brand assets, official domain, and approved visual direction for the home screen, settings, navigation, cards, and buttons. HIMS is out of scope and must never be reintroduced.

## 2. Product experience

- Arabic-first, RTL by default, with English/LTR support.
- Chat-first home screen with a clear task composer.
- Dedicated settings and account experience.
- Consistent navigation, accessible controls, and responsive layouts.
- Agent mode and ordinary chat are distinct product experiences.
- The interface must never imply that an unfinished capability is operational.

## 3. Initial technology baseline

- Client: Expo, React Native, TypeScript, Expo Router, React Native Web.
- API: Python, FastAPI, Pydantic.
- Data platform: Supabase PostgreSQL, Auth, private Storage, Realtime, and RLS.
- Long-running work: separate durable worker process and queue, introduced only after the task contract is designed.
- AI providers: a server-side provider gateway; no provider credentials in the client.
- Observability: structured logs, task traces, usage records, and health checks.

This is a starting baseline, not permission to add paid infrastructure. Prefer free/self-hostable components until cost and operational needs justify otherwise.

## 4. New domain model

Design new tables only when their ownership and access rules are specified. Expected domains include:
- identities and user profiles;
- conversations and messages;
- projects and files;
- task runs, plans, steps, checkpoints, and approvals;
- agent/tool definitions and execution records;
- provider/model catalog and server-side credentials;
- usage, credits, and billing ledger;
- user preferences and audit events.

These are future domain boundaries, not a mandate to create every table in the first migration. Start with the smallest vertical slice and add each domain through reviewed migrations.

## 5. Security baseline

- Supabase publishable key may be used in public clients; secret/service credentials remain server-side.
- RLS is enabled on every user-owned table before it is exposed through the API.
- Every user-owned row is scoped to the authenticated principal.
- Tool execution uses least privilege, explicit allowlists, bounded execution, and approval for consequential actions.
- Secrets are stored server-side and never returned to clients.
- File storage is private by default and access is authorized per object.
- Usage accounting is server-authoritative and idempotent.
- No cross-user data access is allowed.

## 6. Execution model

The central agent will eventually:
1. Understand the request and constraints.
2. Decide whether the request needs a direct response or a plan.
3. Produce a bounded, inspectable task plan.
4. Execute permitted steps with checkpoints and retries.
5. Ask for approval before consequential external actions.
6. Persist progress and partial results.
7. Return a verifiable completion report.

The first release should not claim full autonomous browser or coding capabilities until their isolated runtimes, permission model, persistence, and tests exist.

## 7. Repository and database policy

- `main` is the only working branch.
- The connected Supabase project has been reset for the new product. Keep Supabase-managed schemas intact.
- Do not import old migrations or run old SQL.
- New schema changes must be introduced as forward migrations committed to this repository.
- Never run `db reset` or destructive hosted operations as a routine development step.
- Document the exact state of migrations and the remote schema after each database milestone.

## 8. Definition of done

A feature is complete only when its UI, API, persistence, authorization, error handling, tests, and supported-platform behavior are verified. Screens and mock interactions alone do not satisfy a functional milestone.
