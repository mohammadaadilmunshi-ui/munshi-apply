# Security model

## Principles

- Local-first storage and least privilege.
- No plaintext secrets in extension code, browser bundles, fixtures, logs, or commits.
- Protected facts require explicit confirmation.
- Sensitive changes are auditable.
- Diagnostics redact credentials, tokens, cookies, and session material.
- Security checkpoints remain human-controlled.

## Permission budget

The `0.2.0` extension requests only:

| Permission             | Reason                                                  |
| ---------------------- | ------------------------------------------------------- |
| `sidePanel`            | Persistent application command center                   |
| `storage`              | Extension-owned cache and UI state                      |
| `tabs`                 | Resolve the active tab to its persisted page snapshot   |
| `nativeMessaging`      | Health-checked connection to the local SQLite companion |
| HTTP/HTTPS host access | Inject the universal read-only page sensor              |

`scripting`, `downloads`, and `debugger` are not requested. Native Messaging is limited to the fixed `systems.munshi.apply` host installed for the exact local Edge extension ID.

## Netcup staging deployment permission

The Apply staging transport introduces one infrastructure permission that is intentionally separate from browser/native-host permissions: an ed25519 GitHub Actions deployment key restricted by the server's `authorized_keys` entry to `/opt/munshi/bin/github-apply-staging-deploy-gateway`.

The permission is staging-only and least-privilege by command grammar:

- the forced-command gateway accepts only `/opt/munshi/bin/deploy-apply-staging-release --commit <40-char-sha> --branch <branch>`;
- it has no Hunter deployment route and no production deployment route;
- it has no arbitrary shell or command passthrough;
- the private key exists only as a protected GitHub staging secret and is never installed on Netcup by the bootstrap script;
- source reaches Netcup as a Git bundle created from an exact GitHub branch ref, then the server re-verifies the requested SHA's ancestry before checkout;
- deployment recreates only the Apply staging API service and verifies Hunter staging/production container identities did not change;
- the normal deployment path refuses active prepare/submit proof workers and leaves final review, final submit, and production submit authority disabled;
- the controlled `hosted-submit-proof` profile remains a separate, explicit later operation and is not activated by this transport;
- the one-time bootstrap installer updates only its uniquely tagged Apply staging `authorized_keys` entry and Apply-specific `/opt/munshi/bin` wrappers, with transactional rollback on install failure.

The transport is manual (`workflow_dispatch`) and exact-SHA based. It must not be converted to automatic push/schedule deployment, broadened to production, or changed to an unrestricted SSH key without a new security review and ADR.

See `docs/adr/0001-apply-staging-deployment-transport.md` for the decision record.

## Explicitly prohibited behavior

MUNSHI Apply must not defeat CAPTCHA, MFA, OTP, identity verification, authentication protections, rate limits, bot detection, or anti-abuse controls. It must not interact with hidden honeypot controls. It must not falsify eligibility or protected facts.

## Secrets

Use `apps/native-host/.env.example` only as a variable-name template. Put real values in an ignored `.env` file or the operating system's credential store. Never paste secrets into GitHub issues, pull requests, screenshots, logs, or test fixtures.

Private runtime data belongs under `~/Library/Application Support/MUNSHI Apply/` on macOS, never inside the repository. CI rejects committed databases, credentials, private keys, real résumé files, generated diagnostics, and common secret patterns.

## Reporting

Keep the GitHub repository private during development. If a vulnerability is discovered, document the affected version, impact, reproduction conditions, and proposed containment privately before sharing any exploit detail.
