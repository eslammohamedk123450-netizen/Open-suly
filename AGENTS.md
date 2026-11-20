# SULY repository instructions

SULY is a standalone product. Reuse mature upstream open-source systems when they provide a distinct capability, while keeping SULY's product identity, security boundaries, and control plane authoritative.

## Product identity

Reuse only the approved SULY identity and presentation language:
- Product name, wordmark/monogram, logo assets, and official domain.
- Midnight Gold Luxury visual system: `#080B14`, `#151A27`, `#252B3A`, `#D4AF37`, `#B88A2B`, `#F5F0E2`.

## Architecture and upstream reuse

- Follow [Open-Source Engine Integration Architecture](./docs/architecture/OPEN_SOURCE_ENGINE_INTEGRATION.md).
- Hermes is the primary general-purpose agent runtime; SULY's durable task/DAG, worker leases, retries, cancellation, checkpoints, approvals, audit, usage, auth, and RLS remain authoritative.
- Specialist engines belong in isolated runtimes behind narrow SULY adapters. Do not flatten unrelated upstream repositories into the FastAPI process.
- Reuse complete upstream runtimes where appropriate; pin exact revisions, preserve LICENSE/NOTICE, inspect transitive dependencies, and document provenance.
- Do not claim an engine is integrated until it starts in its intended sandbox and passes adapter/security tests.
- No upstream engine may receive Supabase service credentials, raw DB access, or authority to grant itself permissions.
- Default-deny shell, filesystem, browser, desktop, and external network tools. Require explicit persisted approval scopes and a tested sandbox.
- Screenpipe remains excluded pending license, privacy, consent, retention, and commercial-use review.
- Review AGPL and non-permissive licenses before incorporation, deployment, or distribution.

## Delivery rules

- Work directly on the existing `main` branch only. Never create another branch or PR.
- Build each capability as a new, testable vertical slice.
- Arabic-first with correct RTL; support English and LTR.
- Keep web, Android, and iOS compatibility.
- Never put privileged secrets in the client or Git.
- Enforce authentication, authorization, validation, and RLS at trusted boundaries.
- Do not add paid services, recurring costs, or provider keys without explicit approval.
- Keep upstream versions pinned and commit lockfiles.
- A UI placeholder is not a working AI feature. Clearly separate presentation from implemented functionality.
- Run the relevant typecheck, tests, security checks, and builds before claiming success.

## Milestone report

Report changed files, upstream revisions/licenses, behavior implemented, checks actually run, results, blockers, and whether the milestone exit criteria are met.
