# Delivery roadmap

The Architecture 2.0 baseline defines Phases 0 through 17. Delivery uses smaller verified milestones while the current branch remains in **build-only mode**. Owner-side Edge/native/hosted deployment is intentionally deferred until a consolidated architecture candidate is ready.

## Milestone position

**M0 Foundation — Complete.** Monorepo, contracts, MV3 panel, scanner, IndexedDB, SQLite, and CI are established. The exit gate remains the normal CI, security, migration, and browser workflow set.

**M0.5 Cross-device — Complete foundation.** The responsive private workspace, secure synchronization, phone workflow, and desktop handoff are implemented. The final owner recovery drill belongs to the later physical release campaign.

**M1 Profile & résumé — Advanced/complete foundation.** Protected profile records, résumé vault, hashes, and per-application résumé selection are implemented. Final owner recovery and consolidated deployment remain release work.

**M2 Universal understanding — Advanced.** Frames, open Shadow DOM, sections, navigation, validation, and dynamic fields are implemented broadly. Continued real-ATS compatibility testing belongs to the later physical campaign.

**M3 Pre-flight — Advanced.** Job context, deterministic resolution, sensitive-answer handling, and confidence/review policy are implemented. Richer employer-specific rule extraction remains.

**M4 Verified autofill — Advanced.** Native and custom controls, state waits, upload handoff, interaction verification, rollback, and learned recipe fallback are implemented. Consolidated real-site acceptance remains.

**M5 Multi-step AutoPilot — Advanced.** State machine, checkpoints, navigation, recovery, durable pause/resume, and final-review boundaries are implemented. Crash/interruption and long multi-page physical acceptance remain.

**M6 Intelligence — Major Architecture 2.0 tranche implemented in 0.2.5.** Evidence graph, résumé parsing, hybrid retrieval, provider routing, budgets, job-specific response planning, claim/evidence validation, and writing-style learning are integrated. Physical provider smoke tests are intentionally deferred to consolidated deployment; retrieval quality can continue to improve as more real applications are exercised.

**M7 Learning — Advanced foundation.** Interaction recipes, Teach-MUNSHI, verified promotion, fallback, versioning, and rollback are implemented. Broader site/global/question/user memory composition remains.

**M8 Analytics & orchestration — Foundation.** Ledger, attribution, experiments, and n8n bridge foundations exist. Production UI, exports, and workflows remain.

**M9 Hardening — Ongoing.** Permissions, security, accessibility, performance, backup/restore, privacy, and the final release audit remain the closing campaign.

## Current `0.2.5` build position

- **Foundation / cross-device:** MV3 extension, native companion, encrypted sync, owner workspace, device pairing, profile convergence, résumé storage, migrations, CI, and backup foundations remain intact. Hosted/owner runtime deployment is frozen during the build-only period.
- **Profile / résumé:** Master, Job/Niche Tailored, and Imported résumé classifications are available with SHA-256 identity, selection, reclassification, encrypted deletion, drag/drop, and picker upload.
- **Universal understanding / autofill:** section-aware semantics, repeatable education/employment/certification/language resolution, exact-first option normalization, custom popup handling, dynamic rescanning, all-frame recovery, date/month adaptation, post-action verification, rollback, and learned interaction recipes are present.
- **Pre-flight:** `READY` / `REVIEW` / `UNRESOLVED`, contradiction checks, active-page review scoping, protected-fact handling, salary review, and explicit-only knockout foundations are implemented. Employer-specific rule extraction remains a future enhancement.
- **Multi-page AutoPilot:** persistent Observe → Plan → Act → Verify → Rescan control, durable checkpoints, safe progress before optional review, recoverable fill/navigation pauses, timeouts, Resume, and manual final submission/security boundaries are implemented. Large physical crash/interruption validation is deferred to consolidated deployment.
- **Phase 3 / M6 evidence ingestion:** 0.2.5 locally parses PDF, DOCX, TXT, and MD résumés into SHA-bound `DOCUMENT_CONFIRMED` evidence. Native Messaging uses resumable chunks instead of attempting to send a whole résumé in one message. Legacy `.doc` and image-only/no-text files fail explicitly. DOCX parsing uses hardened XML handling.
- **Phase 3 / retrieval:** hybrid retrieval uses response intent, semantic match, lexical overlap, trust, evidence kind, source diversity, duplicate suppression, and contradiction avoidance. Job-specific response planning expands the query beyond literal employer wording.
- **Phase 8 / provider routing:** provider policy now supports `auto`, `openai`, and local `ollama`. Cheap and strong model lanes can be configured separately. Local Ollama can be the preferred route or fallback; OpenAI remains subject to explicit price and budget gates.
- **Phase 8 / spend accounting:** paid-provider reservations remain concurrent-safe. If a paid provider call fails ambiguously after dispatch, MUNSHI records the conservative reserved estimate rather than pretending no cost was possible. Local Ollama runs record zero provider API cost.
- **Phase 9 / job responses:** Why Company, Why Role, role understanding, relevant experience, career transition, motivation, and behavioral questions have dedicated response plans, evidence requirements, default lengths, and cheap/strong model lanes. Company/role-specific drafts require captured job context.
- **Phase 9 / validation:** every generated factual claim remains evidence-linked and contradiction checked. Consequential semantics such as sponsorship are never converted into AI narrative questions merely because wording also contains a role-motivation phrase.
- **Phase 9 / tone learning:** compact writing preferences are learned only when the owner edits a generated answer and explicitly approves the exact edited draft. Rejected or untouched generations do not train style.
- **Teach-MUNSHI:** demonstration capture is scoped to the selected control and its owned popup. It records value-free event mechanics, redacted before/after state, and a capture quality score. A reusable recipe requires a real answer-state change and commit evidence. Existing SHADOW testing, verified promotion, fallback, versioning, and rollback remain.
- **AI review:** preview, generation, editable draft, evidence/claim display, exact-hash approval, rejection, and mark-used lifecycle remain review-gated before any guarded fill.
- **Learning:** interaction-recipe learning is active. Broader site memory, question learning, cross-site/global pattern composition, and user-correction memory beyond writing-style learning remain future work.
- **Analytics/orchestration:** application outcomes, attribution tokens, experiment assignments, and statistical-honesty foundations exist. Production exports, Tableau-ready datasets, portfolio-event ingestion, experiment UI, and full n8n orchestration remain.
- **Hardening:** secret scanning, repository safety, migrations, native/extension tests, protected sync, Keychain-safe credential writes, and hardened résumé XML parsing are present. Final permission/accessibility/performance/privacy/recovery/backup exercises remain for the release campaign.

## Build sequence after 0.2.5

The next major architecture work should focus on deeper Interaction Escalation + Progressive Learning, then Account Orchestration, Job Signal Intelligence, Attribution/Analytics/n8n, and finally the comprehensive hardening/release campaign.

## Non-negotiable boundaries

No milestone adds automatic final employer submission. CAPTCHA, MFA, OTP, identity verification, authentication/security checkpoints, and operating-system file selection remain owner actions. Connecting any model provider does not authorize unsupported facts, protected claims, or silent generation/fill.
