# Delivery roadmap

The architecture baseline defines Phases 0 through 17. Delivery uses smaller mergeable milestones with measurable gates.

| Milestone                      | Scope                                                                                     | Exit gate                                             |
| ------------------------------ | ----------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| M0 Foundation                  | Monorepo, contracts, MV3 panel, scanner, IndexedDB, SQLite, CI                            | All local and CI checks pass                          |
| M0.5 Cross-device feasibility  | Responsive private workspace, iPhone tests, secure sync design, desktop handoff           | Physical-iPhone workflow gates and threat review pass |
| M1 Profile and résumé vault    | Complete protected profile, résumé hashes, imports, immutable per-application selection   | Round-trip, integrity, and migration tests pass       |
| M2 Universal understanding     | Frame aggregation, Shadow DOM discovery, sections, navigation, validation, dynamic fields | Synthetic lab coverage meets target                   |
| M3 Pre-flight                  | Job context, answer resolver, confidence policy, sensitive answers, preview               | No unresolved/high-risk item can pass silently        |
| M4 Verified autofill           | Native controls, uploads, state waits, post-action verification                           | Every supported interaction has success evidence      |
| M5 Multi-step AutoPilot        | Workflow state machine, checkpoints, recovery, final review                               | Crash and interruption recovery pass                  |
| M6 Intelligence                | Evidence graph, retrieval, provider router, budget engine, generated response validation  | Truth/contradiction and budget tests pass             |
| M7 Learning                    | Recipes, site/global/user memory, shadow promotion, rollback                              | Regression suite prevents known failures              |
| M8 Analytics and orchestration | Ledger, attribution, experiments, exports, n8n                                            | Event, privacy, and statistical-honesty gates pass    |
| M9 Hardening                   | Permission, security, accessibility, performance, backup/restore                          | Release audit passes                                  |

## Current `0.2.0` position

- M0 is complete. Strict CI, browser tests, migration tests, and security workflows are green on the current feature branch.
- M0.5 is complete for the hosted iPhone workspace; the Mac-off physical-device check passed. Edge on iOS does not expose the desktop extension runtime, so iPhone parity is delivered through the hosted owner workspace and a guarded desktop handoff.
- M1 is substantially implemented. The desktop editor exposes a broad structured application profile, coalesces rapid autosaves, explicitly confirms protected facts, synchronizes encrypted profile state with optimistic version checks, preserves confirmed protected facts across device convergence, and includes the encrypted résumé vault. Hosted-workspace field parity plus the final owner recovery-key drill with synthetic data remain release gates before real private-data migration.
- M2 includes all-frame aggregation, open Shadow DOM discovery, stable control fingerprints, History API and semantic-attribute rescanning, grouped radio discovery, and broader deterministic identity/address/education/employment semantics. Broader custom-widget coverage, section/navigation semantics, validation-state modeling, and unusual dynamic controls remain incremental work.
- M3 is implemented for synchronized application reviews and explicit consequential-answer approval. High-risk deterministic questions are never pre-approved merely because a saved fact exists. The mature evidence-backed resolver, contradiction handling, and knockout policy remain tied to M6 retrieval work.
- M4 is implemented for supported native controls with DOM verification, including value-aware radio groups. File controls and unsupported custom widgets remain manual; richer state waits and advanced interaction recipes remain to be added.
- M5 has encrypted application checkpoints and remote reviews, but the full multi-step state machine, interruption recovery, resume-after-checkpoint behavior, and crash recovery are not yet complete.
- M6 now has a secure **provider-configuration foundation**: the desktop native companion can store an OpenAI key in macOS Keychain, test connectivity, discover models, and persist local model/budget controls. Non-secret AI preferences live in the backed-up `settings/` runtime area. No generated application-answer inference is enabled yet. Evidence graph, résumé/evidence parsing, retrieval, context assembly, provider routing for inference, usage metering, budget enforcement, contradiction checking, and generated-response validation remain required before the M6 exit gate can pass.
- M7 and M8 remain future milestones. n8n has a signed event bridge foundation but the full orchestration and analytics workflows are not configured.
- M9 hardening is continuous; source/development verification is now separated from production-runtime verification so the installed environment does not depend on Ruff/Pytest. The final permission, accessibility, performance, backup/restore, security, privacy, and release audits remain future gates.

No milestone may add automatic final submission before the user-configurable final approval checkpoint exists.

Connecting an AI provider does not change the truth boundary: unverified or protected application claims may not be generated, inferred, approved, or filled silently.

Ambiguous generic sponsorship wording remains manual until the profile has a dedicated current-sponsorship fact; it is not substituted from work-authorization, future-sponsorship, or immigration-assistance data.

M0.5 is required before M1 stores real private data in the cloud. It must follow [Mobile and cross-device architecture](MOBILE_AND_CROSS_DEVICE_ARCHITECTURE.md), including the no-paid-service-without-approval rule and the distinction between a mobile foundation build and physical-iPhone verification.
