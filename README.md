# SULY

**More Than AI. Your Intelligent Partner.**

SULY is a new, standalone AI application being built from a clean slate. The retired application is not a foundation for this product; its business logic, APIs, database model, accounts, integrations, and feature systems are out of scope.

## What carries forward

Only the SULY brand identity and approved presentation direction:
- Name, logo/monogram, and official domain.
- Midnight Gold Luxury palette and premium visual language.
- The general look and feel of the home screen, settings, navigation, cards, and buttons.

Everything behind the interface is being designed and implemented specifically for the new SULY product.

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
- [Supabase clean-slate record](./docs/operations/supabase-clean-slate.md)

## Engineering rules

1. SULY is the only product in scope. Do not port or repair retired application logic.
2. HIMS is permanently out of scope.
3. Work directly on `main`; do not create branches or pull requests.
4. Never commit secrets or privileged keys.
5. Enforce authorization and RLS on every user-owned data path.
6. Do not add paid services without explicit approval.
7. Run checks and report only verified results.
8. Add capabilities as new, testable vertical slices.
