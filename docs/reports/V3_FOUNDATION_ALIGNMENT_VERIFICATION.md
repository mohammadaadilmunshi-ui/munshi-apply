# Architecture V3 foundation alignment verification

Verification date: 2026-08-14

Stage: A — Architecture V3 Foundation Alignment

Implementation branch: `feat/v3-foundation-alignment`

## Result

The Stage A source tree passes all local and GitHub gates. The feature branch is published in a draft pull request and remains unmerged. The immutable baseline tag is present and the native runtime has been installed and verified on the owner's Mac. A browser-originated Edge-to-native result and the new physical-iPhone gates remain incomplete.

No autofill, automatic résumé upload, automatic navigation, AutoPilot execution, final submission, AI-generated answers, progressive learning recipes, portfolio attribution, or experiments were implemented.

## Baseline record

| Field         | Verified value                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------ |
| Repository    | `mohammadaadilmunshi-ui/munshi-apply`                                                                              |
| Visibility    | Private                                                                                                            |
| Branch        | `main`                                                                                                             |
| Remote commit | `bcb6caf4e43eaa235cbd77cca468a3d72c58d7c9`                                                                         |
| Baseline tag  | Annotated `v0.1.0` tag object `e8558b8` points to exact baseline commit `bcb6caf4e43eaa235cbd77cca468a3d72c58d7c9` |
| CI run        | [CI run 31767520254](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31767520254)              |
| CI conclusion | Success                                                                                                            |

The baseline CI run covered formatting, lint, TypeScript type checking/tests/build, Python lint/tests, migration execution, and repository-data safety as implemented at that commit. The expanded dependency, secret, migration, and browser workflow set passed on the Stage A feature branch.

## Implementation identity

| Field                         | Value                                                                                                                   |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Local branch                  | `feat/v3-foundation-alignment`                                                                                          |
| Local parent                  | `31f446e` (tree-equivalent publication of remote `bcb6caf4e43eaa235cbd77cca468a3d72c58d7c9`)                            |
| Stage A implementation commit | `83fd963b032813c1b943384d00286911979d2324`                                                                              |
| CI-environment fix commit     | `7b2fe024ebfbfad9a95d7b76e160e309091b9a8b`                                                                              |
| Stage A GitHub branch         | `feat/v3-foundation-alignment`                                                                                          |
| Pull request                  | [Draft PR #11](https://github.com/mohammadaadilmunshi-ui/munshi-apply/pull/11)                                          |
| CI                            | [Success](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31769533390)                              |
| Browser tests                 | [Success](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31769533404)                              |
| Migration tests               | [Success](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31769533443)                              |
| Security                      | [Success, including dependency audits](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31769533392) |

## Schema and persistence changes

Migration `002_transactional_outbox.sql`:

- adds `schema_version`, `correlation_id`, and `payload_sha256` to `application_events`;
- creates `outbox_events` with `PENDING`, `IN_FLIGHT`, `DELIVERED`, `RETRY`, and `DEAD_LETTER` delivery states;
- adds delivery-due and correlation indexes;
- preserves migration idempotency through `schema_migrations`.

SQLite is the authoritative durable store. IndexedDB is explicitly limited to browser cache, active-session state, page snapshots, temporary state, and fast UI state.

Application status transitions can commit the state update, application event, and outbox event in one `BEGIN IMMEDIATE` transaction. A failure rolls back all three. Plain event ingestion atomically commits the ledger and outbox rows, and duplicate `event_id` ingestion is idempotent.

## Event and n8n contract

- Canonical envelope schema version: `1.0`.
- Required identifiers: globally unique `event_id` and workflow `correlation_id`.
- All required Stage A foundation event types are defined in TypeScript and Python.
- Delivery validates the envelope before sending.
- HMAC input: `event_id.timestamp.body_sha256`.
- Requests include the event ID, Unix timestamp, exact-body SHA-256, and HMAC-SHA256 signature.
- Bounded retry intervals are 10 seconds, 30 seconds, 2 minutes, 10 minutes, and 30 minutes before dead-letter review.
- Stale in-flight deliveries are recovered after five minutes.
- n8n is optional; failure cannot block or invalidate the SQLite ledger.
- The downstream rejection and unique-`event_id` idempotency procedure is documented in `docs/N8N_EVENT_CONTRACT.md`.

## Files added

| Area          | Files                                                                                                                                                                                                |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workflows     | `.github/workflows/browser-tests.yml`, `migration-tests.yml`, `security.yml`, `release.yml`                                                                                                          |
| Extension     | `apps/extension/src/messaging/native.ts`                                                                                                                                                             |
| Native host   | `apps/native-host/src/munshi_apply_native/outbox.py`                                                                                                                                                 |
| Tests         | `apps/native-host/tests/test_operations.py`, `test_outbox.py`, `test_settings.py`, `packages/contracts/src/events.test.ts`                                                                           |
| Migration     | `migrations/002_transactional_outbox.sql`                                                                                                                                                            |
| Operations    | `scripts/install.sh`, `install-native-host.sh`, `verify.sh`, `backup.sh`, `update.sh`, `rollback.sh`, `runtime-ops.py`, `release-ops.py`, `repository-safety.sh`, `secret-scan.mjs`, `lib/common.sh` |
| Documentation | `docs/N8N_EVENT_CONTRACT.md`, `docs/RUNTIME_DATA.md`, this report                                                                                                                                    |

## Files modified

| Area          | Files                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Repository    | `.gitignore`, `README.md`, `package.json`, `.github/workflows/ci.yml`                                                  |
| Extension     | `apps/extension/public/manifest.json`, `apps/extension/src/background/service-worker.ts`                               |
| Native host   | `.env.example`, `database.py`, `main.py`, `models.py`, `n8n.py`, `settings.py`                                         |
| Native tests  | `test_api.py`, `test_database.py`, `test_n8n.py`                                                                       |
| Contracts     | `packages/contracts/src/index.ts`                                                                                      |
| Verification  | `scripts/verify-artifacts.mjs`                                                                                         |
| Documentation | `ARCHITECTURE.md`, `CONFIGURATION.md`, `IMPLEMENTATION_STATUS.md`, `SECURITY.md`, `adr/002-durable-extension-state.md` |

## Local verification

| Gate                             | Result                                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------------------------- |
| Prettier                         | Pass — all repository files formatted                                                           |
| ESLint                           | Pass — zero warnings                                                                            |
| TypeScript type checking         | Pass — 5 workspaces                                                                             |
| Vitest                           | Pass — 6 files, 15 tests                                                                        |
| Production build                 | Pass — extension plus 4 TypeScript packages                                                     |
| Extension artifact verification  | Pass — desktop/mobile MV3 permission budgets and 3 entry points each                            |
| Ruff lint and format             | Pass                                                                                            |
| Pytest                           | Pass — 21 tests                                                                                 |
| Total automated tests            | Pass — 36 tests                                                                                 |
| SQLite migrations                | Pass — `001_initial.sql` and `002_transactional_outbox.sql`, repeated run applies zero changes  |
| Repository secret scan           | Pass                                                                                            |
| Private-data boundary            | Pass                                                                                            |
| Native protocol health           | Pass — framed `PING` against isolated migrated SQLite runtime                                   |
| Native manifest generation       | Pass — isolated manifest directory and synthetic valid Edge extension ID                        |
| Backup and checksum verification | Pass — isolated private runtime                                                                 |
| Install script                   | Pass — argument/OS dry run; component operations verified in isolation                          |
| Verify script                    | Pass — isolated runtime health, extension artifacts, SQLite, and source-native protocol path    |
| Rollback script                  | Pass — validated Git ref and non-mutating dry run; database-preservation behavior asserted      |
| Release packaging                | Pass — desktop/mobile Edge ZIPs without source maps, native macOS tarball, manifests, checksums |

## Owner Mac verification evidence

The owner supplied the complete macOS installation transcript for feature-branch commit `b66ca71e3b0d0b2f4e365f7c498eae0e63bedb5f` and unpacked extension ID `mjacegbpedpbiaalkpfjnickiihnliip`.

| Gate              | Evidence                                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Toolchain         | Node `v24.16.0`; Python `3.12.14`; locked npm install reported zero vulnerabilities                                      |
| Extension build   | Production build completed and the original three desktop entry points passed artifact verification                      |
| Runtime location  | Installed outside the repository under the macOS application-support directory                                           |
| Migrations        | `001_initial.sql` and `002_transactional_outbox.sql` applied and reported as expected/applied                            |
| SQLite            | `PRAGMA quick_check` returned `ok`; schema version `002_transactional_outbox.sql`; outbox present with zero pending rows |
| Native protocol   | Direct framed `PING` returned healthy native and database status with the expected migration count                       |
| Edge registration | Native Messaging manifest path and allowed extension ID were validated                                                   |
| Backup            | Backup `20260814T044313Z` was created and checksum-verified                                                              |

The transcript ends after copying the browser-console `NATIVE_HEALTH` test. It does not include that browser-originated result. The screenshot's earlier “Healthy” label was extension-runtime status, not proof of the native connection. The follow-on diagnostics UI now reports extension, native companion, SQLite, outbox, and cloud state separately.

## Follow-on mobile foundation candidate

After Stage A, the local candidate adds a reduced-permission mobile artifact and mobile-aware diagnostics without enabling autofill or final submission:

- the desktop build retains Native Messaging and the Edge side panel;
- `dist-mobile` removes `nativeMessaging`, `sidePanel`, and the side-panel manifest key;
- the mobile action opens the existing responsive UI as a popup;
- artifact verification checks three entry points in each build;
- release operations prepare separate desktop and mobile Edge ZIPs;
- local formatting, lint, type checking, production builds, 15 TypeScript tests, and 21 Python tests pass.

This is build evidence only. Installation, content-script injection, storage, cloud messaging, résumé file handling, background recovery, accessibility, and security-checkpoint behavior must still pass on a physical iPhone running the current Edge App Store build. The binding requirements are in `docs/MOBILE_AND_CROSS_DEVICE_ARCHITECTURE.md`.

## Private mobile workspace checkpoint

The owner-only responsive workspace is deployed at `https://munshi-apply-mobile.mohammadaadilmunshi.chatgpt.site`. Production verification reached the ChatGPT owner sign-in boundary and stopped without requesting credentials.

The deployed candidate includes D1 and R2 bindings, the generated seven-table migration, owner workspace bootstrap, ten-minute one-time pairing challenges, P-256 device-key proof, scoped device credentials, owner revocation, ciphertext-only object upload/download, idempotent sync events, monotonic entity versions, and explicit conflict records. Local lint, TypeScript, Worker artifact validation, rendered HTML, and in-memory SQLite migration integrity checks pass.

The authenticated production API, real D1 migration application, R2 ciphertext round trip, pairing/revocation cycle, recovery key flow, and extension-to-cloud connection remain unverified until the owner completes the production sign-in. Real private data must not be migrated before those gates pass.

### Exact automated test distribution

- TypeScript: 15 tests — application model 2, semantic engine 3, shared 1, event contracts 2, synthetic browser scanner 4, cloud enrollment input validation 3.
- Python: 21 tests — API/event ingestion, migration idempotency, application transition atomicity/rollback, duplicate events, HMAC validation, outbox delivery/retry/dead-letter/stale recovery/schema validation, settings, Native Messaging framing, runtime operations, backup integrity, script dry runs, and release packaging.

## Security result

- No real résumé, profile, credential, database, backup, evidence, or private diagnostic is present in the candidate tree.
- `.gitignore` excludes private runtime roots, databases, secrets, private keys, real résumés, application data, backups, and private diagnostics.
- The repository safety gate rejects common private/credential file classes.
- The secret scan checks tracked and non-ignored worktree files for private keys and common API/token/secret patterns.
- n8n secrets remain local and are never logged or written into release artifacts.
- JavaScript and Python dependency audits passed in the GitHub Security workflow.

## Required external verification before merge

1. Reload the follow-on extension build and capture a browser-originated `NATIVE_HEALTH` result from the installed Edge extension ID.
2. Run the mobile feasibility gates on a physical iPhone using Microsoft's supported Edge extension distribution path.
3. Optionally supply an n8n webhook URL and webhook secret only if external orchestration is desired; core operation does not require them.
4. Merge only after all applicable gates pass and separate merge authorization is provided.

## Known limitations and deferred work

- The repository currently reports `main` branch protection disabled; required checks should be configured before merge enforcement is relied upon.
- The macOS Native Messaging registration and direct native protocol are verified, but a browser-originated Edge-to-native result is not yet recorded.
- The mobile artifact is not a native-host replacement. It requires the Mac-off cloud control plane and physical-iPhone API verification.
- No n8n endpoint was configured; cryptographic signing, validation, failure, and retry behavior were verified locally.
- Rollback preserves the authoritative database and uses versioned code releases. Destructive down-migrations are deliberately unsupported; a target release must remain schema-compatible or use a verified backup/forward migration plan.
- M1 Profile & Résumé Vault has not started. It must use a separate branch only after Stage A merges.
