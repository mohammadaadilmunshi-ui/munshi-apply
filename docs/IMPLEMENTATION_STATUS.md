# Implementation status

Baseline date: 2026-08-14. Release candidate: `0.2.0`.

## Current capabilities

- **MV3 Edge extension — Implemented.** Desktop Edge side panel, service worker, and all-frame content sensors.
- **Hosted iPhone workspace — Deployed and physically verified.** The owner-authenticated responsive workspace works while the Mac is off; the exact deployed frontend source still needs to be imported into Git.
- **Hosted workspace status model — Shared contract implemented.** Device/count loading states, conflict separation, and autosync/manual-sync presentation are regression tested.
- **End-to-end encrypted sync — Implemented.** Owner-held AES-256-GCM key with ciphertext profile, résumé, application, and review events.
- **Device enrollment/revocation — Implemented.** Ten-minute single-use pairing, P-256 proof, scoped credential, and owner revocation.
- **Recovery — Implemented; owner drill pending.** Recovery-key export/import exists; the server cannot recover plaintext or the owner key.
- **Universal DOM/ARIA discovery — Expanded initial implementation.** Native controls, generic comboboxes, injectable frames, and open Shadow DOM.
- **Dynamic observation — Implemented.** Debounced mutation rescans and navigation listeners.
- **Semantic ontology — Initial implementation.** Deterministic high-value rules plus `UNKNOWN`.
- **Protected profile — Expanded desktop implementation.** Structured identity, contact, address, authorization, education, experience, and preference facts with protected confirmation.
- **Profile persistence — Implemented with autosave.** Ordinary facts debounce-save; protected facts confirm on completion; encrypted sync operates when paired.
- **Résumé vault — Implemented.** Client-side encrypted PDF/Word upload, download, and per-review selection.
- **Mobile pre-flight — Implemented.** Review queue, editable answers, and explicit sensitive-answer approval.
- **Guarded fill — Implemented for supported controls.** Approved native controls only; DOM values are verified after browser events.
- **Custom widgets and file controls — Manual fallback.** No false success; employer file picker and unsupported widgets require the owner.
- **Final submission — Manual safety checkpoint.** No automatic final submit, CAPTCHA, MFA, OTP, or identity-verification bypass.
- **Native companion — Verified foundation plus AI secret control.** SQLite, Native Messaging, transactional outbox, and macOS Keychain credential operations.
- **OpenAI configuration — Secure configuration foundation implemented.** Keychain storage, key removal, connection testing, model discovery, and local model/budget controls.
- **AI inference/generated responses — Not enabled.** Evidence retrieval, contradiction checks, usage metering, budget enforcement, and validation remain pending.
- **n8n — Optional and not configured.** Signed HMAC bridge with no dependency for the core workflow.
- **Progressive learning and analytics — Planned.** M7–M8; no behavioral claims in this release.

## Hosted workspace remediation boundary

The hosted workspace status contract is now source-controlled in `@munshi-apply/shared` and `docs/HOSTED_WORKSPACE_UI_CONTRACT.md`. It prohibits the ambiguous `—` count fallback, requires one authority snapshot for overview counters, separates historical conflict events from unresolved conflicts, and makes manual sync a fallback rather than the normal persistence path.

The currently deployed `chatgpt.site` frontend predates that source-control contract. Its visible UI is not considered remediated until the exact hosted source is attached to the repository and the tracked implementation is deployed to the existing runtime, or a separate migration is explicitly authorized.

## AI boundary

The OpenAI configuration foundation does not make the current release an autonomous AI applicant. The API key remains local to the Mac and is never returned by native status calls. Connecting a provider only establishes credentials and controls; application-answer generation stays disabled until M6 evidence, truth, contradiction, and budget gates are implemented and verified.

## iPhone boundary

The iPhone workflow intentionally uses the hosted workspace because current Edge on iOS does not provide the general desktop extension APIs needed to inspect or fill arbitrary employer pages. A paired desktop Edge installation performs those page-bound actions; the iPhone performs the private-data, résumé, review, approval, device, and recovery workflow independently of the Mac.
