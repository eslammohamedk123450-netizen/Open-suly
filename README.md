# SULY

**More Than AI. Your Intelligent Partner.**

SULY is a standalone AI application being built from a clean foundation. Its product behavior, APIs, data models, authentication, AI orchestration, and integrations are designed specifically for SULY.

## Scope boundary

- This repository contains the new, standalone SULY product only.
- HIMS belongs to a discontinued legacy application and is explicitly out of scope: do not preserve, port, integrate, expose, or treat HIMS as a SULY subsystem or requirement.
- Reuse is limited to the approved SULY identity and visual direction described below; legacy application behavior and data are not part of this product.

## Product identity

The product carries the SULY name, logo/monogram, official domain, and approved visual direction:
- Midnight Gold Luxury palette and premium visual language.
- The general look and feel of the home screen, settings, navigation, cards, and buttons.

Everything behind the interface is implemented as part of the new SULY product.

## Current stack

- Client: Expo, React Native, TypeScript, Expo Router, React Native Web.
- API: Python, FastAPI, Pydantic.
- Platform: Supabase PostgreSQL, Auth, private Storage, Realtime, and RLS.
- AI and agent execution: new server-side architecture, introduced in controlled milestones.

## Product direction

Arabic-first with correct RTL, English support, a chat-first home screen, a dedicated settings experience, and a path toward research, task planning, agents, tools, files, and autonomous workflows. UI placeholders are not represented as working AI capabilities.

## Project documents

- [Fresh product architecture](./SULY_MASTER_ARCHITECTURE.md)
- [New delivery roadmap](./SULY_V1_LAUNCH_BLUEPRINT.md)
- [Open-source engine integration architecture](./docs/architecture/OPEN_SOURCE_ENGINE_INTEGRATION.md)
- [Engine adapter contract](./docs/architecture/ENGINE_ADAPTER_CONTRACT.md)
- [Upstream engine inventory](./docs/architecture/UPSTREAM_ENGINE_INVENTORY.md)
- [Supabase clean-slate record](./docs/operations/supabase-clean-slate.md)
- [Agent runtime local smoke test](./docs/testing/AGENT_RUNTIME_SMOKE_TEST.md)
- [Hermes integration status](./docs/architecture/HERMES_CAPABILITY_INTEGRATION_STATUS.md)

## Engineering rules

1. SULY is the only product in scope.
2. Work directly on `main`; do not create branches or pull requests.
3. Never commit secrets or privileged keys.
4. Enforce authorization and RLS on every user-owned data path.
5. Do not add paid services without explicit approval.
6. Run checks and report only verified results.
7. Add capabilities as new, testable vertical slices.
