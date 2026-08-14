# Architecture V3 foundation alignment verification

Verification date: 2026-08-14

Stage: A — Architecture V3 Foundation Alignment

Implementation branch: `feat/v3-foundation-alignment`

## Result

The Stage A source tree passes all local and GitHub gates. The feature branch is published in a draft pull request and remains unmerged. The immutable baseline tag and a real Edge-to-native connection remain release gates and are not represented as complete.

No autofill, automatic résumé upload, automatic navigation, AutoPilot execution, final submission, AI-generated answers, progressive learning recipes, portfolio attribution, or experiments were implemented.

## Baseline record

| Field         | Verified value                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------------------- |
| Repository    | `mohammadaadilmunshi-ui/munshi-apply`                                                                 |
| Visibility    | Private                                                                                               |
| Branch        | `main`                                                                                                |
| Remote commit | `bcb6caf4e43eaa235cbd77cca468a3d72c58d7c9`                                                            |
| Baseline tag  | Not present; the connected GitHub interface does not expose tag creation                              |
| CI run        | [CI run 31767520254](https://github.com/mohammadaadilmunshi-ui/munshi-apply/actions/runs/31767520254) |
| CI conclusion | Success                                                                                               |

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

| Gate                             | Result                                                                                         |
| -------------------------------- | ---------------------------------------------------------------------------------------------- |
| Prettier                         | Pass — all repository files formatted                                                          |
| ESLint                           | Pass — zero warnings                                                                           |
| TypeScript type checking         | Pass — 5 workspaces                                                                            |
| Vitest                           | Pass — 5 files, 12 tests                                                                       |
| Production build                 | Pass — extension plus 4 TypeScript packages                                                    |
| Extension artifact verification  | Pass — MV3 permission budget and 3 entry points                                                |
| Ruff lint and format             | Pass                                                                                           |
| Pytest                           | Pass — 21 tests                                                                                |
| Total automated tests            | Pass — 33 tests                                                                                |
| SQLite migrations                | Pass — `001_initial.sql` and `002_transactional_outbox.sql`, repeated run applies zero changes |
| Repository secret scan           | Pass                                                                                           |
| Private-data boundary            | Pass                                                                                           |
| Native protocol health           | Pass — framed `PING` against isolated migrated SQLite runtime                                  |
| Native manifest generation       | Pass — isolated manifest directory and synthetic valid Edge extension ID                       |
| Backup and checksum verification | Pass — isolated private runtime                                                                |
| Install script                   | Pass — argument/OS dry run; component operations verified in isolation                         |
| Verify script                    | Pass — isolated runtime health, extension artifacts, SQLite, and source-native protocol path   |
| Rollback script                  | Pass — validated Git ref and non-mutating dry run; database-preservation behavior asserted     |
| Release packaging                | Pass — Edge ZIP, native macOS tarball, release manifest, migration manifest, and checksums     |

### Exact automated test distribution

- TypeScript: 12 tests — application model 2, semantic engine 3, shared 1, event contracts 2, synthetic browser scanner 4.
- Python: 21 tests — API/event ingestion, migration idempotency, application transition atomicity/rollback, duplicate events, HMAC validation, outbox delivery/retry/dead-letter/stale recovery/schema validation, settings, Native Messaging framing, runtime operations, backup integrity, script dry runs, and release packaging.

## Security result

- No real résumé, profile, credential, database, backup, evidence, or private diagnostic is present in the candidate tree.
- `.gitignore` excludes private runtime roots, databases, secrets, private keys, real résumés, application data, backups, and private diagnostics.
- The repository safety gate rejects common private/credential file classes.
- The secret scan checks tracked and non-ignored worktree files for private keys and common API/token/secret patterns.
- n8n secrets remain local and are never logged or written into release artifacts.
- JavaScript and Python dependency audits passed in the GitHub Security workflow.

## Required external verification before merge

1. Create the immutable `v0.1.0` tag on remote baseline commit `bcb6caf4e43eaa235cbd77cca468a3d72c58d7c9`.
2. Supply the unpacked Edge extension ID from `edge://extensions` and run the installer on macOS to verify the real Edge-to-native connection.
3. Optionally supply an n8n webhook URL and webhook secret only if external orchestration is desired; core operation does not require them.
4. Merge only after all gates pass and separate merge authorization is provided.

## Known limitations and deferred work

- The repository currently reports `main` branch protection disabled; required checks should be configured before merge enforcement is relied upon.
- A real macOS Native Messaging registration cannot be completed without the machine-generated Edge extension ID.
- No n8n endpoint was configured; cryptographic signing, validation, failure, and retry behavior were verified locally.
- Rollback preserves the authoritative database and uses versioned code releases. Destructive down-migrations are deliberately unsupported; a target release must remain schema-compatible or use a verified backup/forward migration plan.
- M1 Profile & Résumé Vault has not started. It must use a separate branch only after Stage A merges.
