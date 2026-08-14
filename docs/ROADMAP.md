# Delivery roadmap

The architecture baseline defines Phases 0 through 17. Delivery uses smaller mergeable milestones with measurable gates.

| Milestone                      | Scope                                                                                     | Exit gate                                          |
| ------------------------------ | ----------------------------------------------------------------------------------------- | -------------------------------------------------- |
| M0 Foundation                  | Monorepo, contracts, MV3 panel, scanner, IndexedDB, SQLite, CI                            | All local and CI checks pass                       |
| M1 Profile and résumé vault    | Complete protected profile, résumé hashes, imports, immutable per-application selection   | Round-trip, integrity, and migration tests pass    |
| M2 Universal understanding     | Frame aggregation, Shadow DOM discovery, sections, navigation, validation, dynamic fields | Synthetic lab coverage meets target                |
| M3 Pre-flight                  | Job context, answer resolver, confidence policy, sensitive answers, preview               | No unresolved/high-risk item can pass silently     |
| M4 Verified autofill           | Native controls, uploads, state waits, post-action verification                           | Every supported interaction has success evidence   |
| M5 Multi-step AutoPilot        | Workflow state machine, checkpoints, recovery, final review                               | Crash and interruption recovery pass               |
| M6 Intelligence                | Evidence graph, retrieval, provider router, budget engine, generated response validation  | Truth/contradiction and budget tests pass          |
| M7 Learning                    | Recipes, site/global/user memory, shadow promotion, rollback                              | Regression suite prevents known failures           |
| M8 Analytics and orchestration | Ledger, attribution, experiments, exports, n8n                                            | Event, privacy, and statistical-honesty gates pass |
| M9 Hardening                   | Permission, security, accessibility, performance, backup/restore                          | Release audit passes                               |

No milestone may add automatic final submission before the user-configurable final approval checkpoint exists.
