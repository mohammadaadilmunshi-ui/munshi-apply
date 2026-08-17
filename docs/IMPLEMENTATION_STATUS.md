# Implementation status

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
- **Deterministic pre-flight — Advanced.** Central `READY` / `REVIEW` / `UNRESOLVED` resolution, contradiction checks, knockout-rule foundation, salary review, and current-page review scoping are implemented. Richer employer-specific knockout extraction remains future work.
- **Universal Autofill — Advanced.** Text, textarea, contenteditable, native/custom select, radio, checkbox, switch, date/month/time/date-like controls, native/ARIA multi-selects, popup components, all-frame scanning, stale-control rebinding, verification, rollback, and learned-recipe fallback exist.
- **Employer file controls — Owner-controlled verified handoff.** The browser/OS file-selection boundary is not bypassed.
- **Multi-Page AutoPilot — Advanced.** Persistent Observe → Plan → Act → Verify → Rescan runtime, checkpoint-first navigation, durable pause/resume, optional-review progress, recoverable fill/navigation failures, timeout recovery, final-review boundary, and interruption-safe state are implemented. Broad real-site crash/recovery validation remains a release activity.
- **Teach-MUNSHI — Strengthened in 0.2.5.** User demonstration, value-free action recipes, SHADOW testing, verified promotion, versioning, fallback, and rollback are live. Capture now records scoped event classes/timing plus redacted before/after state and quality evidence. Unrelated page clicks cannot create a reusable recipe, and demonstrated answer text is not persisted in the capture.
- **Provider-agnostic intelligence — Implemented foundation expanded in 0.2.5.** OpenAI Responses and local Ollama adapters share structured claim/evidence output. AI settings support `auto`, `openai`, and `ollama`, cheap/strong model lanes, local fallback, owner evidence permissions, and paid-provider budget policy.
- **AI budget/pricing — Implemented.** Paid-provider generation requires explicit pricing and budget permission. Reservations account for concurrent requests; ambiguous provider failures consume a conservative estimated reservation rather than silently undercounting possible spend. Local Ollama usage records zero provider API cost.
- **Job-specific response planning — Implemented in 0.2.5.** Why Company, Why Role, role understanding, relevant experience, career transition, motivation, behavioral, and other narrative intents have evidence requirements, retrieval vocabulary, answer-length defaults, and cheap/strong model routing.
- **Job-context requirement — Implemented.** Company/role-dependent drafts require captured job/company evidence. Candidate evidence alone cannot manufacture a company-specific answer.
- **Generated-answer truth validation — Implemented.** Structured claims must point to supplied evidence IDs; contradiction and word-limit validation remain enforced. Consequential semantic types such as sponsorship cannot be reclassified into a narrative AI question merely because the wording also contains a phrase such as “why this role.”
- **Writing-style learning — Implemented foundation in 0.2.5.** MUNSHI learns compact style preferences only from a generated draft that the owner actually edits and explicitly approves. Rejected or untouched drafts do not train the preference profile.
- **AI review lifecycle — Implemented.** Preview, Generate Draft, edit, exact-hash approval, rejection, and mark-used state are available. Generated answers remain review-gated before guarded fill.
- **OpenAI credential handling — Implemented foundation.** macOS Keychain storage/removal, connection testing, model discovery, and local non-secret settings are present. A real physical provider/Keychain smoke test is deferred to consolidated deployment.
- **Ollama local fallback — Implemented foundation.** Loopback-only model discovery and structured generation are supported. Physical local-model validation is deferred to consolidated deployment.
- **Progressive learning — Advanced foundation.** Structural fingerprints, recipe attempts, verified promotion, rollback, and Teach-MUNSHI are implemented. Broader site/global/question/user memory composition remains future work.
- **Analytics/experiments — Foundation implemented.** Application outcomes, attribution tokens, deterministic assignments, variants, and minimum-sample statistical-honesty gates exist. Production exports/UI and portfolio-event ingestion remain future work.
- **Native companion — Advanced.** SQLite, migrations, Native Messaging protocol v3, transactional outbox, backups, Keychain operations, profile/evidence/checkpoint/usage persistence, chunked document ingestion, provider routing, AI draft lifecycle, writing-style learning, and learning/analytics persistence are covered by native/migration CI.
- **n8n — Signed bridge foundation only.** Production orchestration workflows remain future work.
- **Final submission and security checkpoints — Manual boundaries.** MUNSHI does not automatically submit an employer application and does not solve/bypass CAPTCHA, MFA, OTP, identity verification, authentication, or operating-system security controls.

## Intelligence boundary during build-only mode

0.2.5 has a complete synthetic path from résumé/job evidence → retrieval → response intent → provider/model route → structured claim/evidence draft → validation → owner review/approval. This is **not an owner-side deployment claim**. No real provider request/spend or physical Ollama/OpenAI production acceptance is required during the build-only period. Those physical gates are deferred to the consolidated deployment tranche.

## Remaining architecture emphasis

The largest remaining architecture areas are account orchestration, deeper interaction escalation/visual fallback, broader progressive site/global/question memory, Job Signal Intelligence, artifact attribution, experiment/analytics presentation and exports, production n8n workflows, and final security/recovery/performance/accessibility hardening.

## iPhone boundary

The iPhone workflow intentionally uses the hosted workspace because Edge on iOS does not expose the desktop extension APIs required to inspect/fill arbitrary employer pages. A paired desktop Edge installation performs page-bound actions; the iPhone handles private data, résumé, review, approval, device, and recovery workflows.
