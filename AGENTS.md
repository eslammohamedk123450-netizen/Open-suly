# SULY repository instructions

SULY is a brand-new, standalone product. Treat all previous application logic, data models, APIs, and database objects as nonexistent. Do not port or repair the retired implementation.

## What may be reused

Reuse only the established SULY brand identity and approved presentation language:
- Product name, wordmark/monogram, logo assets, and official domain.
- Midnight Gold Luxury visual system: `#080B14`, `#151A27`, `#252B3A`, `#D4AF37`, `#B88A2B`, `#F5F0E2`.
- General visual direction of the home screen, settings, navigation, cards, and buttons where an approved visual reference exists.

Do not reuse old business logic, database tables, RPCs, edge functions, user accounts, feature flags, credit balances, provider settings, agent implementations, or HIMS code. HIMS is permanently out of scope.

## Delivery rules

- Work directly on the existing `main` branch only. Never create another branch or PR.
- Build the new product from a clean architecture; do not make the old application the foundation.
- Arabic-first with correct RTL; support English and LTR.
- Keep web, Android, and iOS compatibility.
- Never put privileged secrets in the client or Git.
- Enforce authentication, authorization, validation, and RLS at trusted boundaries.
- Do not add paid services or recurring costs without explicit approval.
- Keep changes small, testable, and documented.
- A UI placeholder is not a working AI feature. Clearly separate presentation from implemented functionality.
- Run the relevant typecheck, tests, and builds before claiming success.

## Milestone report

Report changed files, behavior implemented, checks actually run, results, blockers, and whether the milestone exit criteria are met.
