# ADR 0001: Standalone SULY clean-slate architecture

- Status: Accepted
- Date: 2026-11-20

## Context

The prior application is retired and is not a foundation for SULY. The new product must be built independently. Only the SULY brand identity, official domain, and approved visual language may carry forward.

## Decision

- Rebuild all product behavior, APIs, data models, authentication flows, AI orchestration, and integrations from a clean slate.
- Reuse only the SULY name/mark, Midnight Gold visual identity, and approved presentation patterns for the home screen, settings, navigation, cards, and buttons.
- Client: Expo, React Native, TypeScript, Expo Router, and React Native Web.
- API: Python, FastAPI, and Pydantic.
- Platform: Supabase PostgreSQL, Auth, private Storage, Realtime, and RLS.
- Experience: Arabic-first RTL with English/LTR support.
- Delivery: small vertical slices with explicit tests and exit criteria.

## Non-goals

- No HIMS system.
- No migration of previous application business logic.
- No reuse of previous user accounts, credits, provider records, tools, workflows, or database schema.
- No claim that a UI placeholder is a working AI capability.

## Constraints

1. Work directly on the existing `main` branch.
2. Keep privileged secrets server-side.
3. Enforce authorization at trusted server and database boundaries.
4. Do not add paid services without explicit owner approval.
5. Verify behavior on supported platforms before marking a milestone complete.

## Consequences

SULY starts with a minimal identity schema and a new app shell. All product capabilities must be designed, implemented, and tested for this product. The architecture can evolve as measured requirements become clear.
