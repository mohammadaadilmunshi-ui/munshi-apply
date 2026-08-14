# Implementation status

Baseline date: 2026-08-14. Release candidate: `0.2.0`.

| Architecture capability            | Status                                      | Implementation                                                                                    |
| ---------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| MV3 Edge extension                 | Implemented                                 | Desktop Edge side panel, service worker, all-frame content sensors                                |
| Hosted iPhone workspace            | Implemented and physically verified         | Owner-authenticated responsive workspace remains available while the Mac is off                   |
| End-to-end encrypted sync          | Implemented                                 | Owner-held AES-256-GCM key; ciphertext profile, résumé, application, and review events            |
| Device enrollment/revocation       | Implemented                                 | Ten-minute single-use pairing, P-256 proof, scoped credential, owner revocation                   |
| Recovery                           | Implemented, owner drill pending            | Recovery-key export/import; server cannot recover plaintext or the owner key                      |
| Universal DOM/ARIA discovery       | Expanded initial implementation             | Native controls, generic comboboxes, injectable frames, and open Shadow DOM                       |
| Dynamic observation                | Implemented                                 | Debounced mutation rescans and navigation listeners                                               |
| Semantic ontology                  | Initial implementation                      | Deterministic high-value rules plus `UNKNOWN`                                                     |
| Protected profile                  | Expanded desktop implementation             | Structured identity/contact/address/auth/education/experience/preferences; protected confirmation |
| Profile persistence                | Implemented with autosave                   | Ordinary facts debounce-save; protected facts confirm on completion; encrypted sync when paired   |
| Résumé vault                       | Implemented                                 | Client-side encrypted PDF/Word upload, download, and per-review selection                         |
| Mobile pre-flight                  | Implemented                                 | Review queue, editable answers, explicit sensitive-answer approval                                |
| Guarded fill                       | Implemented for supported controls          | Approved native controls only; DOM value verified after browser events                            |
| Custom widgets and file controls   | Manual fallback                             | No false success; employer file picker and unsupported widgets require the owner                  |
| Final submission                   | Manual safety checkpoint                    | No automatic final submit, CAPTCHA, MFA, OTP, or identity-verification bypass                     |
| Native companion                   | Verified foundation plus AI secret control  | SQLite, Native Messaging, transactional outbox, macOS Keychain credential operations              |
| OpenAI configuration               | Secure configuration foundation implemented | Keychain storage, key removal, connection test, model discovery, local model/budget controls      |
| AI inference / generated responses | Not enabled                                 | Evidence retrieval, contradiction checks, usage metering, budget enforcement, validation pending  |
| n8n                                | Optional, not configured                    | Signed HMAC bridge; no dependency for the core workflow                                           |
| Progressive learning and analytics | Planned                                     | M7–M8; no behavioral claims in this release                                                       |

The OpenAI configuration foundation does not make the current release an autonomous AI applicant. The API key remains local to the Mac and is never returned by native status calls. Connecting a provider only establishes credentials and controls; application-answer generation stays disabled until M6 evidence, truth, contradiction, and budget gates are implemented and verified.

The iPhone workflow intentionally uses the hosted workspace because current Edge on iOS does not provide the general desktop extension APIs needed to inspect or fill arbitrary employer pages. A paired desktop Edge installation performs those page-bound actions; the iPhone performs the complete private-data, résumé, review, approval, device, and recovery workflow independently of the Mac.
