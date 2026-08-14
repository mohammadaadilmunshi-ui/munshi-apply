# Implementation status

Baseline date: 2026-08-14. Release candidate: `0.2.0`.

| Architecture capability            | Status                              | Implementation                                                                         |
| ---------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------- |
| MV3 Edge extension                 | Implemented                         | Desktop Edge side panel, service worker, all-frame content sensors                     |
| Hosted iPhone workspace            | Implemented and physically verified | Owner-authenticated responsive workspace remains available while the Mac is off        |
| End-to-end encrypted sync          | Implemented                         | Owner-held AES-256-GCM key; ciphertext profile, résumé, application, and review events |
| Device enrollment/revocation       | Implemented                         | Ten-minute single-use pairing, P-256 proof, scoped credential, owner revocation        |
| Recovery                           | Implemented, owner drill pending    | Recovery-key export/import; server cannot recover plaintext or the owner key           |
| Universal DOM/ARIA discovery       | Expanded initial implementation     | Native controls, generic comboboxes, injectable frames, and open Shadow DOM            |
| Dynamic observation                | Implemented                         | Debounced mutation rescans and navigation listeners                                    |
| Semantic ontology                  | Initial implementation              | Deterministic high-value rules plus `UNKNOWN`                                          |
| Protected facts                    | Implemented                         | Explicit confirmation, protected classifications, encrypted synchronization            |
| Résumé vault                       | Implemented                         | Client-side encrypted PDF/Word upload, download, and per-review selection              |
| Mobile pre-flight                  | Implemented                         | Review queue, editable answers, explicit sensitive-answer approval                     |
| Guarded fill                       | Implemented for supported controls  | Approved native controls only; DOM value verified after browser events                 |
| Custom widgets and file controls   | Manual fallback                     | No false success; employer file picker and unsupported widgets require the owner       |
| Final submission                   | Manual safety checkpoint            | No automatic final submit, CAPTCHA, MFA, OTP, or identity-verification bypass          |
| Native companion                   | Verified foundation                 | Authoritative SQLite, Native Messaging, transactional outbox                           |
| n8n                                | Optional, not configured            | Signed HMAC bridge; no dependency for the core workflow                                |
| AI provider router                 | Not configured                      | Requires separate provider and budget approval; no paid provider enabled               |
| Progressive learning and analytics | Planned                             | M7–M8; no behavioral claims in this release                                            |

The iPhone workflow intentionally uses the hosted workspace because current Edge on iOS does not provide the general desktop extension APIs needed to inspect or fill arbitrary employer pages. A paired desktop Edge installation performs those page-bound actions; the iPhone performs the complete private-data, résumé, review, approval, device, and recovery workflow independently of the Mac.
