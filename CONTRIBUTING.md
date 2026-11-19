# Contributing to SULY

Thank you for helping build SULY. Changes must follow the architecture documents and the repository rules in [AGENTS.md](./AGENTS.md).

## Before changing code

1. Read [README.md](./README.md), [SULY_MASTER_ARCHITECTURE.md](./SULY_MASTER_ARCHITECTURE.md), and [SULY_V1_LAUNCH_BLUEPRINT.md](./SULY_V1_LAUNCH_BLUEPRINT.md).
2. Inspect the current implementation and identify the milestone being worked on.
3. Confirm that the change preserves HIMS and existing user data.
4. Identify security, migration, cost, and cross-platform implications.

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

## Verification

Run the checks relevant to the files changed. Report commands that were actually executed and their results. If a check cannot run because dependencies, credentials, or infrastructure are unavailable, state that clearly rather than marking it as passed.

## Security and costs

Do not commit credentials or real environment files. Do not add paid infrastructure, paid APIs, or recurring costs without explicit approval from the repository owner.
