# MUNSHI Apply — Architecture V3 Implementation Status

Baseline date: 2026-08-17. Current build candidate: `0.2.5`.

## Operating mode

MUNSHI Apply is currently in **build-only mode**. Source changes are committed and verified in CI, but the owner-side Edge extension, native companion, and hosted workspace are not redeployed after every tranche. A consolidated deployment and physical acceptance cycle will happen after the planned architecture build is complete.

## Current capabilities

- **MV3 Edge extension — Implemented.** Desktop Edge side panel, service worker, all-frame content sensors, runtime reinjection/recovery, dynamic scanning, and broad application-state understanding.
- **Hosted iPhone workspace — Implemented and previously physically verified.** The owner-authenticated responsive workspace works independently of the Mac for private profile, résumé, review, device, recovery, and application-state workflows. Hosted deployment is intentionally not being refreshed during the current build-only period.
- **End-to-end encrypted sync — Implemented.** Owner-held AES-256-GCM key with ciphertext profile, résumé, application, and review events.
- **Device enrollment/revocation — Implemented.** Single-use pairing, proof, scoped credential, and owner revocation.
- **Recovery — Implemented; final owner recovery drill remains a release gate.**
- **Universal page understanding — Advanced.** Native/ARIA controls, accessible frames, open Shadow DOM, dynamic mutation/history rescans, custom popup/list/tree/grid controls, section-aware semantics, repeatable application records, validation-state modeling, and application-route detection are present.
- **Protected Master Profile — Implemented across desktop and hosted clients.** Identity/contact/address, education, employment, project, certification, language, authorization, sponsorship, preferences, disclosure, and voluntary demographic facts use typed storage and protected confirmation where required.
- **Résumé vault — Advanced.** Master, Job/Niche Tailored, and Imported classifications; encrypted storage; SHA-256 identity; drag/drop and picker upload; per-application selection; reclassification; deletion/tombstones; and employer picker handoff are implemented.
- **Résumé evidence ingestion — Implemented in 0.2.5.** PDF, DOCX, TXT, and MD files can be parsed locally into source-bound `DOCUMENT_CONFIRMED` evidence. Legacy `.doc` and image-only/no-text documents fail explicitly rather than being guessed. Native Messaging ingestion is resumable/chunked and verifies the original résumé SHA-256 before indexing. DOCX XML parsing uses hardened XML handling.
- **Evidence Graph — Advanced.** Durable evidence nodes/edges, trust levels, protected-evidence exclusion, contradiction relationships, source identity, and generated-text separation remain authoritative.
- **Hybrid evidence retrieval — Implemented in 0.2.5.** Retrieval combines semantic intent, query overlap, trust, evidence kind, job/candidate evidence needs, source diversity, duplicate suppression, and contradiction avoidance. Job-response planning expands retrieval beyond literal question words.
- **Deterministic pre-flight — Advanced.** Central `READY` / `REVIEW` / `UNRESOLVED` / `BLOCKED` resolution, contradiction checks, explicit employer-rule extraction, current-page knockout checks, salary review, and current-page review scoping are implemented.
- **Account orchestration — Implemented foundation.** Generic login/create/recovery/verification classification, portal-scoped account metadata, duplicate-account detection, Workday tenant separation, application linkage, native lookup/upsert, and AutoPilot owner handoff are implemented. Authentication secrets remain outside the account registry.
- **Universal Autofill — Advanced.** Text, textarea, contenteditable, native/custom select, radio, checkbox, switch, date/month/time/date-like controls, native/ARIA multi-selects, popup components, all-frame scanning, stale-control rebinding, verification, rollback, and learned-recipe fallback exist.
- **Employer file controls — Owner-controlled verified handoff.** The browser/OS file-selection boundary is not bypassed.
- **Multi-Page AutoPilot — Advanced.** Persistent Observe → Plan → Act → Verify → Rescan runtime, checkpoint-first navigation, durable pause/resume, optional-review progress, recoverable fill/navigation failures, timeout recovery, final-review boundary, account/security boundaries, explicit current-page knockout blocking, and interruption-safe state are implemented. Broad real-site crash/recovery validation remains a release activity.
- **Teach-MUNSHI — Strengthened in 0.2.5.** User demonstration, value-free action recipes, SHADOW testing, verified promotion, versioning, fallback, and rollback are live. Capture records scoped event classes/timing plus redacted before/after state and quality evidence. Unrelated page clicks cannot create a reusable recipe, and demonstrated answer text is not persisted in the capture.
- **Interaction escalation — Advanced foundation.** Promoted recipe, native control, ARIA, keyboard, structural popup, state-transition, SHADOW recipe, and controlled visual-assisted fallback are ordered behind reversible-action, sensitivity, security, reachability, and final-submit gates.
- **Progressive learning — Advanced foundation.** Site, Question, Failure, Success, User Correction, and Global Pattern memories; verified-outcome confidence; aging; versioning; conflict review; sensitive/global reuse restrictions; and durable memory observations are implemented.
- **Provider-agnostic intelligence — Implemented foundation expanded in 0.2.5.** OpenAI Responses and local Ollama adapters share structured claim/evidence output. AI settings support `auto`, `openai`, and `ollama`, cheap/strong model lanes, local fallback, owner evidence permissions, and paid-provider budget policy.
- **AI budget/pricing — Implemented.** Paid-provider generation requires explicit pricing and budget permission. Reservations account for concurrent requests; ambiguous provider failures consume a conservative estimated reservation rather than silently undercounting possible spend. Local Ollama usage records zero provider API cost.
- **Job-specific response planning — Implemented in 0.2.5.** Why Company, Why Role, role understanding, relevant experience, career transition, motivation, behavioral, and other narrative intents have evidence requirements, retrieval vocabulary, answer-length defaults, and cheap/strong model routing.
- **Job-context requirement — Implemented.** Company/role-dependent drafts require captured job/company evidence. Candidate evidence alone cannot manufacture a company-specific answer.
- **Generated-answer truth validation — Implemented.** Structured claims must point to supplied evidence IDs; contradiction and word-limit validation remain enforced. Consequential semantic types such as sponsorship cannot be reclassified into a narrative AI question merely because the wording also contains a phrase such as “why this role.”
- **Writing-style learning — Implemented foundation in 0.2.5.** MUNSHI learns compact style preferences only from a generated draft that the owner actually edits and explicitly approves. Rejected or untouched drafts do not train the preference profile.
- **AI review lifecycle — Implemented.** Preview, Generate Draft, edit, exact-hash approval, rejection, and mark-used state are available. Generated answers remain review-gated before guarded fill.
- **OpenAI credential handling — Implemented foundation.** macOS Keychain storage/removal, connection testing, model discovery, and local non-secret settings are present. A real physical provider/Keychain smoke test is deferred to consolidated deployment.
- **Ollama local fallback — Implemented foundation.** Loopback-only model discovery and structured generation are supported. Physical local-model validation is deferred to consolidated deployment.
- **Analytics/experiments — Foundation implemented.** Application outcomes, attribution tokens, deterministic assignments, variants, and minimum-sample statistical-honesty gates exist. Production exports/UI and portfolio-event ingestion remain future work.
- **Native companion — Advanced.** SQLite, migrations, Native Messaging protocol v3, transactional outbox, backups, Keychain operations, profile/evidence/checkpoint/usage persistence, chunked document ingestion, provider routing, AI draft lifecycle, writing-style learning, interaction/progressive learning, account metadata, and analytics persistence are covered by native/migration CI.
- **n8n — Signed bridge foundation only.** Production orchestration workflows remain future work.
- **Final submission and security checkpoints — Manual boundaries.** MUNSHI does not automatically submit an employer application and does not solve/bypass CAPTCHA, MFA, OTP, identity verification, authentication, password entry, credential storage, or operating-system security controls.

## Completed coupled tranche — Interaction Escalation + Progressive Learning

- Deterministic escalation ladder from promoted interaction recipes through native/ARIA/keyboard/structural/state-transition techniques to guarded visual-assisted fallback.
- Visual-assisted fallback remains reversible, non-sensitive, and post-action verified.
- Authentication, security checkpoints, unreachable frames, and final employer submission remain hard boundaries.
- Component fingerprint v2 includes Shadow DOM/frame depth, portals, virtualization, popup ownership, framework hints, multi-select/contenteditable behavior, with legacy fallback.
- Site, Question, Failure, Success, User Correction, and Global Pattern memory.
- Confidence changes from verified outcomes; owner corrections supersede prior interpretations.
- Aging, versioning, conflict review, and sensitive-question global-reuse restrictions.
- Migration `008_progressive_memory.sql` and durable native progressive-memory store.

## Completed coupled tranche — Account Orchestration + Employer Pre-flight Intelligence

### Account orchestration

- Generic classification of candidate account surfaces into login, create-account, recovery, verification, unknown-auth, or no-account flow.
- Employer portal scope is explicit. Shared ATS hosts are not treated as one universal account; Workday tenant path identity is included to prevent cross-employer account reuse.
- Duplicate-account detection prefers an existing account for the same portal scope instead of creating another candidate identity.
- Durable metadata-only account registry and application linkage via migration `009_account_orchestration.sql`.
- Native Messaging exposes account lookup/upsert and advertises the `account_orchestration` capability.
- The extension AutoPilot Control Center reads known account metadata and shows the current account boundary, portal scope, duplicate risk, and required owner action.
- After the owner completes a login/create/verification step, the extension can record account metadata and the application link for future reuse.
- Passwords, credentials, secrets, tokens, passcodes, and OTPs are not columns in the account registry, are rejected if sent to the account store, and are not autonomous AutoPilot actions. Embedded URL credentials are rejected.
- MFA, OTP, identity verification, account recovery, password entry, authentication, and final submission remain explicit owner boundaries.

### Employer-specific pre-flight intelligence

- Deterministic extraction of explicit employer requirements from captured job/application context for work authorization, sponsorship, U.S. citizenship, security clearance, degree, experience, salary, start date, travel, relocation, and work mode.
- Generic questions such as “Will you require sponsorship?” do not become knockout rules by themselves; MUNSHI requires explicit employer language such as no-sponsorship or authorization-required statements.
- Confirmed work-authorization/sponsorship answers are compared against explicit current-page knockout requirements before AutoPilot can act.
- Deterministic contradictions hard-block AutoPilot. Unresolved or non-deterministic requirements remain REVIEW/UNRESOLVED rather than being guessed.
- Degree thresholds use normalized degree levels without inventing equivalency.
- Experience thresholds are not calculated from résumé dates unless a verified total-experience fact exists; otherwise they remain review items.
- Salary compatibility remains review intelligence rather than an automatic rejection.
- Start-date, travel, relocation, work-mode, clearance, and citizenship requirements use confirmed facts where available and fail closed to review/unresolved when evidence is insufficient.

## Current verification

At canonical head `50370fc8d29142ee20331bbff472dc668163933d`, all five standard PR workflows passed before this documentation-only status update:

- CI ✅
- Browser tests ✅
- Security ✅
- Migration tests ✅
- Owner workspace ✅

Verified results at that source head:

- **54 TypeScript/JavaScript test files / 326 tests passed.**
- **113 native Python tests passed; Ruff passed.**
- Prettier, ESLint, TypeScript, production builds, repository-safety checks, and artifact verification passed.
- **3 desktop + 3 mobile extension entry points** verified.
- CI dependency install reported **0 npm vulnerabilities**.
- Secret scan passed for **334 tracked files**.
- Fresh unpacked Edge artifact: ID `9298225349`, SHA-256 `0629030f96e7580fdfde8703aa8532315a45be53e9258223d0cf58f17a27d9a3`.

## Intelligence boundary during build-only mode

0.2.5 has a complete synthetic path from résumé/job evidence → retrieval → response intent → provider/model route → structured claim/evidence draft → validation → owner review/approval. This is **not an owner-side deployment claim**. No real provider request/spend or physical Ollama/OpenAI production acceptance is required during the build-only period. Those physical gates are deferred to the consolidated deployment tranche.

## Remaining architecture emphasis

The largest remaining program areas are:

1. Job Signal Intelligence.
2. Analytics, attribution, experiment presentation/exports, portfolio-event ingestion, and production n8n workflows.
3. Real OpenAI/Ollama provider and Mac Keychain smoke testing, including routing/fallback/latency/budget/output validation.
4. Broad real-ATS endurance, crash/interruption, reload, dynamic-page, and recovery validation.
5. Final security, recovery, accessibility, performance, privacy, and backup/restore hardening.
6. Consolidated deployment and physical acceptance, including final owner-workspace/profile continuity validation.

## Release boundary

The canonical source is intentionally ahead of the owner-installed Edge/native/hosted runtimes. This remains build-only until the remaining architecture tranches are complete and one controlled deployment/acceptance campaign is performed.

Do not treat source/CI completion as physical release acceptance. Real ATS/provider smoke testing, broad endurance testing, account-flow physical testing, owner recovery, accessibility/performance/privacy review, backup/restore drills, and consolidated physical release testing remain later gates.

Final employer submission, CAPTCHA/MFA/OTP/identity/authentication/security checkpoints, password/credential actions, and operating-system file selection remain owner actions.

## iPhone boundary

The iPhone workflow intentionally uses the hosted workspace because Edge on iOS does not expose the desktop extension APIs required to inspect/fill arbitrary employer pages. A paired desktop Edge installation performs page-bound actions; the iPhone handles private data, résumé, review, approval, device, and recovery workflows.
