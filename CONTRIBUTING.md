# Contributing to SULY

Thank you for helping build SULY. Changes must follow [AGENTS.md](./AGENTS.md), [the architecture](./SULY_MASTER_ARCHITECTURE.md), and [the delivery roadmap](./SULY_V1_LAUNCH_BLUEPRINT.md).

## Before changing code

1. Read the product scope and current milestone.
2. Inspect the current implementation before editing.
3. Confirm that the change is for the new standalone SULY product.
4. Identify security, migration, cost, and cross-platform implications.
5. Reuse only approved brand and presentation elements; do not port retired application logic.

## Branch policy

All project work is committed directly to the existing `main` branch. Do not create additional branches or pull requests.

## Implementation standards

- Keep changes small and focused.
- Use clear names and consistent formatting.
- Validate data at API and persistence boundaries.
- Enforce authorization server-side and through RLS where applicable.
- Never expose privileged secrets to browser or mobile clients.
- Add tests for new behavior and regression tests for bug fixes.
- Update documentation when behavior, configuration, or operations change.
- A screen mockup or placeholder is not a completed backend capability.

## Verification

Run checks relevant to the files changed. Report commands actually executed and their results. If a check cannot run because dependencies, credentials, or infrastructure are unavailable, state that clearly.

## Security and costs

Do not commit credentials or real environment files. Do not add paid infrastructure, paid APIs, or recurring costs without explicit approval from the repository owner.
