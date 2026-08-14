# Implementation status

Baseline date: 2026-08-14.

| Architecture capability      | Status                                | Implementation                                                                                 |
| ---------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------- |
| MV3 Edge extension           | Implemented                           | `apps/extension`                                                                               |
| Mobile-safe Edge artifact    | Foundation candidate                  | Reduced-permission `apps/extension/dist-mobile`; physical iPhone not yet verified              |
| Persistent side panel        | Implemented                           | Application, profile, diagnostics views                                                        |
| Responsive private workspace | Foundation candidate                  | Mobile-first owner workspace; cloud deployment and authentication not yet complete             |
| Service-worker durability    | Implemented                           | IndexedDB cache for active UI/page state                                                       |
| Universal DOM/ARIA discovery | Initial implementation                | Native controls and generic comboboxes                                                         |
| Dynamic observation          | Initial implementation                | Debounced `MutationObserver` rescans                                                           |
| Multi-frame sensors          | Initial implementation                | Content script injected into all eligible frames                                               |
| Semantic ontology            | Initial implementation                | Deterministic high-value rules plus `UNKNOWN`                                                  |
| Protected facts              | Initial implementation                | Explicit local profile facts and review flags                                                  |
| Application state model      | Initial implementation                | Valid transition contract                                                                      |
| Native companion             | V3 foundation candidate               | Authoritative SQLite, Native Messaging, outbox                                                 |
| n8n                          | Interface implemented, not configured | Optional signed HMAC webhook with bounded retry                                                |
| Private runtime operations   | V3 foundation candidate               | Install, verify, backup, update, rollback, release                                             |
| Cross-device cloud sync      | Foundation candidate, not connected   | Owner-only control plane, ciphertext objects, idempotent events, and explicit conflict records |
| Device enrollment/revocation | Foundation candidate                  | Ten-minute single-use pairing, P-256 key proof, scoped credential, owner revocation API        |
| Résumé vault                 | Planned                               | M1                                                                                             |
| Pre-flight                   | Planned                               | M3                                                                                             |
| Autofill and verification    | Not enabled                           | M4                                                                                             |
| AutoPilot                    | Not enabled                           | M5                                                                                             |
| AI provider router           | Planned                               | M6                                                                                             |
| Progressive learning         | Planned                               | M7                                                                                             |
| Analytics/experiments        | Planned                               | M8                                                                                             |

“Initial implementation” means the architecture boundary is operational but has not yet met the full release target in the master plan.

“Foundation candidate” for mobile means the build and responsive UI pass local automated checks. It does not mean that Edge on iOS supports every required extension API. Physical-device installation, injection, storage, file, navigation, accessibility, and security-checkpoint tests remain mandatory before the mobile workflow can be described as fully functional.
