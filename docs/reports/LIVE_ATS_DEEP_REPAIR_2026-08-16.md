# Live ATS deep repair — 2026-08-16

## Scope

This repair was driven by physical Levin application testing rather than synthetic controls alone.

The repaired paths cover custom dropdown prompt recovery, radio-group prompt recovery, graduation-date recognition, employer-specific date formatting, controlled radio and checkbox interaction, owner-entered pre-flight draft preservation, LinkedIn referral defaults, salary acceptance resolution, résumé file-picker handoff, and evidence-grounded AI drafting.

## AI grounding

AI drafting now receives bounded visible employer-page context and confirmed non-protected profile and profile-record evidence at request time. This removes the requirement that a matching evidence-graph node must already have been seeded before a supported application question can be drafted.

The encrypted résumé file itself is not parsed by this repair. Résumé-like evidence comes from confirmed employment, project, education, certification, responsibility, achievement, and related profile records.

## Safety boundaries

Final employer submission, CAPTCHA, MFA, OTP, identity verification, authentication, and operating-system file selection remain owner actions. Salary acceptance is only filled when it can be resolved from an explicit saved answer or a compatible confirmed numeric preference.

## Verification

The functional source repair was published as `bbd211301b7c33ef8aa4c2f911f2477292cfc96d` after the dedicated repair gate passed formatting, lint, TypeScript checks, 39 JavaScript/TypeScript test files with 249 tests, production build, artifact verification, secret scanning, Ruff, and the native-host Pytest suite.

PR #11 remains draft, open, and unmerged.
