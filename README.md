# SULY

**More Than AI. Your Intelligent Partner.**

SULY is an independent agentic AI application. It is developed as a standalone product and does not depend on, embed, or inherit functionality from any previous application or unrelated system.

## Product direction

- Arabic-first experience with English support.
- Web, Android, and iOS clients built from a shared Expo + React Native + TypeScript codebase.
- Chat-first user experience with a distinct agent execution mode.
- A modular Python + FastAPI backend.
- Supabase PostgreSQL, Auth, private Storage, Realtime, and Row Level Security (RLS).
- Durable background workers for long-running tasks, checkpoints, retries, and cancellation.
- A unified model/provider gateway with controlled fallbacks and cost tracking.
- Explicit permissions and approvals for consequential actions.

## Core platform capabilities

The SULY product scope includes task planning and DAG execution, research, browser workflows, coding in isolated environments, files and document generation, data analysis, image generation, integrations and workflows, memory and projects, usage accounting, administration, and operational observability.

A capability is not considered complete merely because its interface exists. It must be connected to a working implementation and covered by appropriate tests.

## Architecture and delivery

The authoritative architecture and launch requirements are documented in:

- [SULY_MASTER_ARCHITECTURE.md](./SULY_MASTER_ARCHITECTURE.md)
- [SULY_V1_LAUNCH_BLUEPRINT.md](./SULY_V1_LAUNCH_BLUEPRINT.md)

Implementation proceeds through the milestones and exit criteria in those documents. Work is committed directly to the existing `main` branch. Do not create additional branches.

## Non-negotiable engineering rules

1. SULY is the only product in scope. Do not import or preserve unrelated legacy application modules.
2. HIMS and its activation, content, and resource features are out of scope and must not be reintroduced.
3. Never commit secrets, API keys, service-role keys, private certificates, or real environment files.
4. Enforce authorization on the server and with database RLS; never rely on client-side checks alone.
5. Validate inputs and outputs at trust boundaries.
6. Add tests for meaningful behavior and security-sensitive changes.
7. Do not claim a feature, deployment, test, or integration works unless it has been verified.
8. Do not introduce paid services or material recurring costs without explicit approval.
9. Keep the application usable across supported web and mobile targets.
10. Document architectural decisions and breaking changes.
11. Prefer small, reviewable, reversible changes.

## Development status

This repository is the source of truth for the standalone SULY implementation. Check the milestone documents and current repository state before making changes. Report blockers honestly and include verification evidence with each completed milestone.

## Supabase environment baseline

The connected Supabase project already contains an established schema and live data. Read [the verified project baseline](./docs/operations/supabase-existing-project-baseline.md) before changing database objects or migrations. Do not recreate or reset the database. Remove legacy/HIMS database objects only through reviewed forward migrations after checking dependencies and preserving SULY-owned data.

## Security

See [SECURITY.md](./SECURITY.md) for vulnerability reporting guidance.
