# Autofill Hardening Verification — 2026-08-14

## Scope

This report records the completed MUNSHI Apply autofill-hardening tranche on `feat/v3-foundation-alignment`.

The tranche strengthens guarded application interaction without changing the permanent owner-control boundaries. Final employer submission remains manual. CAPTCHA, MFA, OTP, authentication, identity verification, security checkpoints, and operating-system file selection remain owner actions. Autofill does not invent application facts or silently truncate/rewrite employer answers.

## Implemented hardening

- ATS-aware adaptive waits and DOM-stability checks.
- Deterministic semantic option equivalence without fuzzy guessing.
- Native select/radio/date handling with exact post-action verification and rollback.
- Async/portaled ARIA option handling and React-style control rebinding after rerenders.
- ARIA switch, checkbox, radio, and exact multi-select interaction.
- Strict canonical `month`, `time`, `datetime-local`, and ISO-week controls without locale/time-zone guessing.
- Open-shadow custom-calendar and option discovery.
- Employer validation classification and fail-closed handling for required/format/length/range/pattern/file validation.
- Repeated/indexed control metadata without auto-creating employment, education, or other records.
- Dependent-field protection: newly appearing required controls force a fresh plan/review instead of stale forward navigation.
- Owner-assisted file-picker flow plus local SHA-256 fingerprinting after explicit file selection; local filesystem paths are not learned or transmitted.
- Desktop `webNavigation` lifecycle support for iframe/page invalidation while keeping the mobile permission budget at `storage` + `tabs`.
- Verified interaction result metadata for strategy, verification, rebinding, stabilization, and component fingerprint.
- Native interaction-recipe lookup and verified-outcome telemetry for safe widget mechanics only. Recipe learning rejects sensitive/consequential semantics and unsafe strategies, stores no answer values, and promotes/rolls back only from verified outcomes.
- Stale native outbox recovery made independent of wall-clock drift by making recovered retry rows immediately eligible.

## Guarded certification

The temporary final-autofill integration workflow completed the following gates before creating the certified source commit:

- Prettier formatting check: passed.
- ESLint with zero warnings: passed.
- TypeScript checks across workspaces: passed.
- JavaScript/TypeScript tests: **190 passed across 34 test files**.
- Production extension build: passed.
- Desktop/mobile artifact verification: passed.
- Secret scan: passed.
- Native Ruff check: passed.
- Native Python tests: **88 passed**.

Certified implementation commit:

`3f2a93dbd2f665302cf22a1d26274f5af9a4342f` — `feat: complete advanced autofill hardening`

The temporary helper workflow and patch script self-removed after certification and are not part of the finished source tree.

## Deliberate limitations

This certification is automated repository/runtime verification, not a physical Microsoft Edge owner smoke test on the user’s Mac. Real ATS websites can still introduce novel closed-shadow, cross-origin, anti-bot, or vendor-specific widgets that should fail closed and be added through future verified compatibility work rather than guessed around.

Interaction recipes currently provide safe lookup plus verified success/failure learning for eligible mechanics. They do not authorize consequential answers, security bypasses, autonomous final submission, or arbitrary learned browser actions.

## Release boundary

PR #11 remains a **draft**. This report does not authorize merging. A separate explicit owner authorization is required before any merge.
