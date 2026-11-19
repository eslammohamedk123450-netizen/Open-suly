# SULY repository instructions

SULY is a standalone product built from a clean foundation.

## Product identity

Reuse only the approved SULY identity and presentation language:
- Product name, wordmark/monogram, logo assets, and official domain.
- Midnight Gold Luxury visual system: `#080B14`, `#151A27`, `#252B3A`, `#D4AF37`, `#B88A2B`, `#F5F0E2`.
- Approved visual direction for the home screen, settings, navigation, cards, and buttons.

All functional behavior, APIs, data models, authentication, AI orchestration, integrations, and background execution must be designed specifically for SULY.

## Delivery rules

- Work directly on the existing `main` branch only. Never create another branch or PR.
- Build each capability as a new, testable vertical slice.
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
