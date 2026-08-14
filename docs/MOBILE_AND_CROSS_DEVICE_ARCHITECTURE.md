# Mobile and cross-device architecture

Status: implementation contract for the first private iPhone release.

## Locked product requirements

- Support the latest generally available iOS and Microsoft Edge versions.
- Provide the same user outcome on iPhone and desktop: understand an application, resolve every question, select evidence, prepare answers, fill supported controls, verify the result, and stop for deliberate final approval.
- Remain usable when the Mac is off.
- Synchronize the full private workspace, including résumés, evidence, application state, and protected facts.
- Prepare the first Edge Add-ons release as a hidden listing.
- Use no chargeable service or plan without the owner's explicit approval.

“Same user outcome” does not mean that iOS exposes every desktop browser API. A mobile workflow may use the extension popup, a responsive private workspace, or a verified handoff when an Edge API is unavailable. The workflow may not claim that an action occurred unless it has success evidence.

## Runtime model

| Runtime                      | Role                                                                           | Authority while online                           | Offline behavior                                                   |
| ---------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------ | ------------------------------------------------------------------ |
| Edge extension on macOS      | Page discovery, preview, verified interactions, desktop UI                     | Cloud workspace plus native companion            | Uses IndexedDB session cache and the Mac SQLite journal            |
| Native companion on macOS    | Local durable journal, Native Messaging, backups, local file access            | Mac replica; submits idempotent changes to cloud | Continues locally and queues an outbox                             |
| Edge extension on iOS        | Page discovery and supported interactions through mobile-safe extension APIs   | Cloud workspace                                  | Keeps only bounded, encrypted session/cache state                  |
| Responsive private workspace | Profile, résumé, application, pre-flight, review, and device-management UI     | Cloud workspace                                  | Read-only cached shell where supported; no false completion claims |
| Cloud control plane          | Cross-device state, encrypted object references, convergence, and audit events | Durable cross-device authority                   | Always available independently of the Mac                          |

The iPhone must never depend on the Python native host. Microsoft Native Messaging is a desktop integration, so the mobile build removes `nativeMessaging` and `sidePanel` and uses the existing responsive UI as its action popup or tab surface.

## Data plane

Structured workspace state is stored separately from file objects:

- D1-compatible relational storage holds accounts, devices, applications, immutable profile versions, protected-fact records, answer decisions, résumé metadata, event envelopes, outbox acknowledgements, and conflict records.
- R2-compatible object storage holds encrypted résumé and evidence bytes.
- SQLite remains the durable Mac journal and local replica; it is no longer the only authority once cloud sync is enabled.
- IndexedDB remains a non-authoritative browser cache and active-session store.

Every mutation carries a globally unique event ID, correlation ID, schema version, device ID, logical entity version, timestamp, and payload hash. Cloud ingestion is idempotent. A device retries from its outbox until the cloud acknowledges the exact event ID.

## Encryption and protected data

The first release may synchronize all private data only after these controls exist:

1. Transport encryption for every request.
2. Server-side encryption supplied by the hosting platform.
3. Application-layer encryption for résumé/evidence objects and protected-fact payloads before durable cloud storage.
4. Per-user data-encryption keys wrapped by a recoverable owner key; no plaintext key in source control, logs, analytics, or release artifacts.
5. Explicit device enrollment and revocation, short-lived sessions, and a device inventory visible to the owner.
6. Encrypted backup, key-recovery, restore, and disaster-recovery tests before real data is migrated.
7. Redacted diagnostics by default, with private export only after deliberate owner action.

Protected facts are versioned and immutable. A conflict creates a review record; neither cloud nor device silently overwrites a protected fact. Résumé selection is frozen per application version and changes only after explicit confirmation.

## Authentication and device connection

The private workspace begins as owner-only access through the hosting platform's supported sign-in. Extension access requires a separate device-enrollment flow:

1. The owner signs in to the private workspace.
2. The workspace displays a short-lived, single-use pairing challenge.
3. The extension proves possession of a generated device key and exchanges the challenge for a scoped, revocable device credential.
4. Credentials are stored only in the platform's secure extension/device storage available on that runtime.
5. The workspace lists the device, last use, capabilities, and a revoke action.

No long-lived bearer secret is copied into source, configuration documentation, or browser-readable page content.

## Conflict and convergence policy

- Append-only application and audit events merge by event ID.
- Ordinary editable metadata uses optimistic concurrency with an explicit base version.
- Protected facts, résumé choices, final-review decisions, and submission state never use last-write-wins.
- Conflicting consequential values pause the workflow and appear in one pre-flight review.
- A device may display “synced” only after the cloud acknowledges its current version.
- A completed interaction requires post-action evidence from the target page; a queued intent is not completion.

## Human checkpoints

MUNSHI Apply pauses for CAPTCHA, MFA, OTP, identity verification, authentication, and any other security control. It also pauses before final submission. It does not bypass, solve, outsource, or falsely report those checkpoints.

The normal workflow is:

1. Observe and map the complete application.
2. Resolve known questions from evidence.
3. Present one pre-flight review for unresolved, sensitive, contradictory, or protected items.
4. Preview the planned actions and selected résumé.
5. Fill only supported controls and verify each result.
6. Present a final review and wait for deliberate submit approval.

## iPhone feasibility gates

Full mobile release is blocked until all gates pass on a physical iPhone using the current Edge App Store build:

| Gate         | Required evidence                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------- |
| Installation | Hidden Edge Add-ons listing can be installed or otherwise enabled through Microsoft's supported iOS flow |
| Injection    | Content scripts run on normal HTTPS application pages and report the expected origin/frame data          |
| Storage      | Required extension storage persists across browser restart without exposing secrets                      |
| UI           | Popup/tab workspace is usable at supported iPhone viewport sizes and with VoiceOver/text scaling         |
| Messaging    | Extension-to-cloud requests authenticate, retry safely, and reject replayed or expired credentials       |
| Files        | A résumé can be selected through supported iOS controls, uploaded with user awareness, and verified      |
| Navigation   | Multi-step pages preserve workflow identity and recover after Edge backgrounding                         |
| Safety       | CAPTCHA/MFA/OTP and final submission always remain manual checkpoints                                    |
| Parity       | Unsupported Edge APIs produce an honest guided fallback instead of a silent failure                      |

Passing a desktop build or an iOS simulator is not enough. Until these gates pass, the mobile artifact is a foundation candidate, not a promise of universal iPhone autofill.

## Release and cost policy

The first store release is a hidden Edge Add-ons listing. Hidden controls discoverability; it does not remove Microsoft review, policy, privacy, security, or mobile-compatibility requirements.

Developer registration and submission are currently documented by Microsoft as free. Hosting, database, object storage, email, observability, AI providers, and traffic may have free allowances but can later incur usage charges. MUNSHI Apply must start within available no-cost allowances and must not enable a paid plan, paid add-on, or billable external provider without the owner's explicit approval.

## Delivery sequence

1. Keep the verified desktop/native foundation stable.
2. Ship and test the reduced-permission mobile artifact on a physical iPhone.
3. Build owner-only cloud records and encrypted object upload with synthetic data.
4. Add device pairing, revocation, idempotent sync, and conflict review.
5. Migrate a copy of private data only after backup and recovery drills pass.
6. Complete end-to-end desktop and iPhone application tests without final submission.
7. Prepare privacy disclosures, support material, release ZIPs, and the hidden listing.
8. Submit or publish only after separate owner authorization.
