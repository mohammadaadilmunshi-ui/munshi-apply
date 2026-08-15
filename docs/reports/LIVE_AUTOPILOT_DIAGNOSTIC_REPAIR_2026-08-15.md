# Live AutoPilot diagnostic repair — 2026-08-15

## Scope

An owner Edge smoke test showed the AutoPilot screen on a résumé step reporting a blocked pre-flight while safe approved fills and an owner-controlled file handoff were present.

Permanent boundaries remain unchanged: final employer submission, CAPTCHA, MFA, OTP, identity verification, authentication, and operating-system file selection remain owner actions.

## Diagnostic findings

1. Passive or invisible anti-bot integration could be mistaken for an active CAPTCHA because the scanner accepted any matching iframe/class/id and hidden page text. ATS pages can preload reCAPTCHA assets before a challenge is actually presented.
2. Navigation detection considered hidden buttons, so a later hidden final-submit control could incorrectly classify an earlier application step as a final-submission boundary.
3. The side-panel file-picker request crosses extension/background/content-script contexts. Browser transient user activation is not guaranteed to survive that asynchronous path, so a direct `input.click()` can be ignored even though the request was delivered.
4. The owner UI exposed the internal checkpoint sentinel `-1` and did not identify which detected hard boundary caused a blocked pre-flight.
5. `docs/IMPLEMENTATION_STATUS.md` lagged the current live AutoPilot controller and verified file-handoff implementation.

## Repairs

- Security checkpoint detection now uses visible security text plus active challenge heuristics. Passive reCAPTCHA integration no longer blocks a normal application step; visible active challenges remain fail-closed owner checkpoints.
- Hidden navigation controls are excluded from navigation and final-submit inference.
- File upload handoff retains the direct picker request and adds an isolated on-page MUNSHI owner prompt. If Edge rejects the cross-context request, the owner can click the on-page prompt so the employer picker is opened by a direct browser user gesture. MUNSHI still never chooses a local file or captures a local filesystem path.
- AutoPilot diagnostics show an em dash before the first checkpoint and surface detected security/final boundaries explicitly.
- Current implementation-status documentation was aligned with the live guarded runtime.

## Regression coverage

Automated coverage now verifies passive reCAPTCHA does not create a checkpoint, an active visible challenge still does, hidden final-submit controls cannot mark an earlier résumé step as final submission, the resilient owner file handoff does not select a file, and disabled file controls fail closed.

## Verification

The isolated repair workflow completed successfully as GitHub Actions run `31867984482`. Before publishing source commit `7837912680e8342369efeaee12a31d5f082ccb3a`, it completed locked dependency installation, Prettier, ESLint, workspace TypeScript checks, the complete Vitest suite, production builds, desktop/mobile artifact verification, secret scanning, native companion installation, Ruff, the complete native Pytest suite, and the repository private-data boundary.

A follow-up owner-authenticated documentation commit is used only to re-trigger the repository's normal pull-request workflow suite against the repaired branch head, because GitHub suppresses or marks PR workflows as action-required when the preceding branch update is made by `github-actions[bot]`.

Automated verification cannot substitute for a physical Edge smoke test on the exact employer page, especially for browser user-activation and third-party anti-bot behavior.
