# ADR 0001: SULY architecture baseline

- Status: Accepted as the implementation baseline
- Date: 2026-11-20
- Scope: Initial repository foundation

## Context

SULY is intended to become a cross-platform agentic AI product. It must support a chat-first experience and real task execution while maintaining security, durable operations, and controlled operating costs.

## Decision

The initial implementation baseline is:

- **Clients:** Expo, React Native, TypeScript, Expo Router, and React Native Web.
- **API:** Python, FastAPI, and Pydantic, organized as a modular monolith initially.
- **Data and identity:** Supabase PostgreSQL, Auth, private Storage, Realtime, and Row Level Security.
- **Long-running work:** Separate durable workers with persisted task state, checkpoints, bounded retries, leases, and safe cancellation.
- **AI providers:** A unified server-side gateway with provider adapters, policy controls, fallback rules, and usage accounting.
- **Experience:** Arabic-first, RTL-aware, with English support.
- **Delivery:** Milestone-based implementation with explicit exit criteria and verification.

## Constraints

1. Work directly on the existing `main` branch; do not create other branches.
2. HIMS remains a core system and must not be removed, disabled, or bypassed.
3. Privileged secrets stay server-side and must never be committed.
4. Authorization must be enforced at trusted server and database boundaries.
5. New paid services or recurring costs require explicit owner approval.
6. A feature is complete only after implementation and verification, not when a placeholder UI is added.

## Consequences

This baseline favors a maintainable first release while leaving room to split services when measured load or operational needs justify it. The modular monolith is not permission to place long-running work inside short-lived request handlers; durable workers remain a required platform component.

Changes to this baseline require a new architecture decision record and must preserve the non-negotiable constraints above.
