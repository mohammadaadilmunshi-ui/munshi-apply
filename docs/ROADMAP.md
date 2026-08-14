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

- M0 is complete and verified locally.
- M0.5 is complete for the hosted iPhone workspace; the Mac-off physical-device check passed. Edge on iOS does not expose the desktop extension runtime, so iPhone parity is delivered through the hosted owner workspace and a guarded desktop handoff.
- M1 is implemented; the final owner recovery-key drill with synthetic data remains a release gate before real private-data migration.
- M2 includes all-frame aggregation and open Shadow DOM discovery. Broader custom-widget coverage remains incremental.
- M3 is implemented for synchronized application reviews and explicit sensitive-answer approval.
- M4 is implemented for supported native controls with DOM verification. File controls and unsupported custom widgets remain manual.
- M5 has encrypted application checkpoints and remote reviews, but multi-step crash recovery is not yet complete.
- M6–M8 remain future milestones and require separate approval before any paid AI or external service is enabled.

No milestone may add automatic final submission before the user-configurable final approval checkpoint exists.

M0.5 is required before M1 stores real private data in the cloud. It must follow [Mobile and cross-device architecture](MOBILE_AND_CROSS_DEVICE_ARCHITECTURE.md), including the no-paid-service-without-approval rule and the distinction between a mobile foundation build and physical-iPhone verification.
