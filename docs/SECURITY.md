# Security model

## Principles

- Local-first storage and least privilege.
- No plaintext secrets in extension code, browser bundles, fixtures, logs, or commits.
- Protected facts require explicit confirmation.
- Sensitive changes are auditable.
- Diagnostics redact credentials, tokens, cookies, and session material.
- Security checkpoints remain human-controlled.

## Permission budget

The `0.1.0` extension requests only:

| Permission             | Reason                                                |
| ---------------------- | ----------------------------------------------------- |
| `sidePanel`            | Persistent application command center                 |
| `storage`              | Extension-owned state and future settings             |
| `tabs`                 | Resolve the active tab to its persisted page snapshot |
| HTTP/HTTPS host access | Inject the universal read-only page sensor            |

`nativeMessaging`, `scripting`, `downloads`, and `debugger` are not requested until a shipped feature needs them and receives a separate review.

## Explicitly prohibited behavior

MUNSHI Apply must not defeat CAPTCHA, MFA, OTP, identity verification, authentication protections, rate limits, bot detection, or anti-abuse controls. It must not interact with hidden honeypot controls. It must not falsify eligibility or protected facts.

## Secrets

Use `apps/native-host/.env.example` only as a variable-name template. Put real values in an ignored `.env` file or the operating system's credential store. Never paste secrets into GitHub issues, pull requests, screenshots, logs, or test fixtures.

## Reporting

Keep the GitHub repository private during development. If a vulnerability is discovered, document the affected version, impact, reproduction conditions, and proposed containment privately before sharing any exploit detail.
