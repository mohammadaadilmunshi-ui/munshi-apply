# Implementation status

Baseline date: 2026-08-14. Release candidate: `0.2.0`.

## Current capabilities

- **MV3 Edge extension — Implemented.** Desktop Edge side panel, service worker, and all-frame content sensors.
- **Hosted iPhone workspace — Deployed and physically verified.** The owner-authenticated responsive workspace works while the Mac is off and can display the enrolled desktop device; the exact deployed frontend source still needs to be imported into Git before hosted parity can be treated as reproducible.
- **Hosted workspace status model — Shared contract implemented.** Device/count loading states, conflict separation, autosync/manual-sync presentation, and active-review-backlog semantics are regression tested. The live `chatgpt.site` frontend is not yet claimed to consume all of those shared rules because its exact source is not in this repository.
- **End-to-end encrypted sync — Implemented.** Owner-held AES-256-GCM key with ciphertext profile, résumé, application, and review events.
- **Device enrollment/revocation — Implemented.** Ten-minute single-use pairing, P-256 proof, scoped credential, and owner revocation.
- **Recovery — Implemented; owner drill pending.** Recovery-key export/import exists; the server cannot recover plaintext or the owner key. A synthetic fresh-client recovery drill remains a release gate before full real private-data migration.
- **Universal DOM/ARIA discovery — Expanded initial implementation.** Native controls, generic comboboxes, injectable frames, open Shadow DOM, stable control fingerprints, and dynamic rescanning.
- **Dynamic observation — Implemented.** Debounced mutation rescans, semantic-attribute changes, form input/change signals, and History API navigation listeners.
- **Semantic ontology — Expanded deterministic implementation.** Identity, contact, address, education, employment, authorization, sponsorship, preference, and protected/high-risk concepts plus `UNKNOWN`. Explicit current sponsorship and future sponsorship are distinct; ambiguous generic sponsorship remains manual.
- **Protected profile — Expanded desktop implementation.** Structured identity, contact, address, authorization, sponsorship, education, experience, and preference facts with protected confirmation. Additive contracts now define repeatable education/employment/project/certification/language records for the next durable-storage/UI migration.
- **Profile persistence — Implemented with autosave and convergence safety.** Ordinary facts debounce-save; protected facts confirm deliberately; stale in-flight saves cannot mark newer edits synchronized; protected cross-device conflicts do not silently last-write-win.
- **Résumé vault — Strengthened.** Client-side encrypted PDF/DOC/DOCX uploads are size/type validated. New uploads record SHA-256 of the original bytes plus family/version/source metadata, and application reviews record the selected résumé hash when available so the exact selected bytes can be identified. Existing legacy résumé records remain readable.
- **Deterministic pre-flight resolver — Implemented and wired into the desktop UI.** A central resolver returns `READY`, `REVIEW`, or `UNRESOLVED`; missing or unmapped facts are not invented, generated/non-authoritative facts cannot become ready answers, and protected/sensitive/high-risk facts require review.
- **Review backlog model — Implemented as a shared contract.** Current review work can be scoped to active application pages and latest review state, preventing historical discovered questions from being legitimately counted as current unresolved work. Live hosted adoption remains pending with the hosted frontend source-control gap.
- **Guarded fill — Implemented for supported controls.** Approved native text, textarea, select, radio, checkbox, contenteditable, and open-Shadow-DOM controls are filled only when supported and verified through the DOM afterward. Radio groups are value-aware. Ambiguous checkbox values fail without changing the page.
- **Custom widgets and employer file controls — Manual fallback.** No false success; unsupported custom controls and employer file pickers require the owner. The encrypted résumé vault does not imply automatic employer upload interaction.
- **Final submission — Manual safety checkpoint.** No automatic final submit, CAPTCHA, MFA, OTP, identity-verification, or security-checkpoint bypass.
- **Evidence/retrieval foundation — Initial deterministic implementation.** Evidence nodes/edges, trust-aware bounded retrieval, protected-evidence exclusion by default, generated-text exclusion from authoritative retrieval, and contradiction-edge detection exist. Résumé/evidence parsing, durable evidence graph storage, richer context assembly, and full contradiction evaluation remain.
- **Native companion — Verified foundation plus AI secret control.** SQLite, Native Messaging, transactional outbox, backups, runtime verification, and macOS Keychain credential operations.
- **OpenAI configuration — Secure configuration foundation implemented.** Keychain storage, key removal, connection testing, model discovery, and local model/budget controls. Non-secret AI preferences are backed up under `settings/`. The Keychain write path no longer places the plaintext API key in process arguments; a physical Mac Keychain smoke test remains before using a real key.
- **AI inference/generated responses — Not enabled.** Provider inference routing, usage metering, enforceable budget accounting, context assembly, unsupported-claim detection, contradiction validation, and generated-response validation remain pending.
- **AutoPilot — State/checkpoint groundwork only.** State contracts and synchronized application snapshots exist, but the persistent Observe → Plan → Act → Verify → Rescan controller, navigation/recovery engine, and crash/interruption recovery are not complete.
- **n8n — Optional and not configured.** Signed HMAC bridge with no dependency for the core workflow.
- **Progressive learning and analytics — Planned.** M7–M8; no behavioral claims in this release.

## Hosted workspace remediation boundary

The hosted workspace status contract is source-controlled in `@munshi-apply/shared` and `docs/HOSTED_WORKSPACE_UI_CONTRACT.md`. It prohibits the ambiguous `—` count fallback, requires one authority snapshot for overview counters, separates historical conflict events from unresolved conflicts, makes manual sync a fallback rather than the normal persistence path, and now defines active-scope review backlog semantics so historical discovered questions are not presented as current review work.

Physical evidence shows the phone-hosted workspace can display `1 paired device`, while an earlier desktop-hosted view displayed `— paired devices`. That narrows the fault to hosted frontend state consumption/rendering rather than the underlying device enrollment. The currently deployed `chatgpt.site` frontend predates the source-control contract. Its visible UI is not considered fully remediated until the exact hosted source is attached to the repository and the tracked implementation is deployed to the existing runtime, or a separate migration is explicitly authorized.

The hosted-source investigation established that `apps/owner-workspace/` is absent from the canonical repository, no matching source exists in the expected local Mac project/download/document locations, and unauthenticated access to the deployed site returns HTTP 401 without recoverable public source maps. A safe signed-in browser probe exists for the next recovery step.

## AI boundary

The OpenAI configuration foundation does not make the current release an autonomous AI applicant. The API key remains local to the Mac and is never returned by native status calls. Connecting a provider only establishes credentials and controls; application-answer generation stays disabled until M6 evidence, truth, contradiction, usage, budget, and response-validation gates are implemented and verified.

## iPhone boundary

The iPhone workflow intentionally uses the hosted workspace because Edge on iOS does not provide the general desktop extension APIs needed to inspect or fill arbitrary employer pages. A paired desktop Edge installation performs those page-bound actions; the iPhone performs the private-data, résumé, review, approval, device, and recovery workflow independently of the Mac.
