# SULY

**More Than AI. Your Intelligent Partner.**

SULY is an agentic AI platform designed to help people research, plan, create, analyze, and execute real tasks through a unified, secure, and observable system.

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

The long-term product scope includes task planning and DAG execution, research, browser workflows, coding in isolated environments, file and document generation, data analysis, image generation, integrations, projects, memory, usage accounting, administration, and operational observability.

A capability is not considered complete merely because its interface exists. It must be connected to a working implementation and covered by appropriate tests.

## Architecture and delivery

The authoritative architecture and launch requirements are documented in:

- [SULY_MASTER_ARCHITECTURE.md](./SULY_MASTER_ARCHITECTURE.md)
- [SULY_V1_LAUNCH_BLUEPRINT.md](./SULY_V1_LAUNCH_BLUEPRINT.md)

Implementation proceeds through the milestones and exit criteria in those documents. Work is committed directly to the existing `main` branch. Do not create additional branches.

## Non-negotiable engineering rules

1. Preserve existing product capabilities and data. Do not remove, bypass, or disable HIMS.
2. Never commit secrets, API keys, service-role keys, private certificates, or real environment files.
3. Enforce authorization on the server and with database RLS; never rely on client-side checks alone.
4. Validate inputs and outputs at trust boundaries.
5. Add tests for meaningful behavior and security-sensitive changes.
6. Do not claim a feature, deployment, test, or integration works unless it has been verified.
7. Do not introduce paid services or material recurring costs without explicit approval.
8. Keep the application usable across supported web and mobile targets.
9. Document architectural decisions and breaking changes.
10. Prefer small, reviewable, reversible changes.

## Development status

This repository is the source of truth for the SULY implementation. Check the milestone documents and current repository state before making changes. Report blockers honestly and include verification evidence with each completed milestone.

## Security

See [SECURITY.md](./SECURITY.md) for vulnerability reporting guidance once the security policy is published.
