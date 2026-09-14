# Final AutoApply continuation — 2026-09-14

## Safety boundary

Source/test/CI only. No deployment, production DB mutation, real applications, mail, or final-submit activation. GitHub connector is authoritative; never retry unauthenticated Git or request credentials.

## Verified source anchors

- Hunter: release/initial-dashboard-hunter-rc-v2-20260913 at eb61d05490a738327db20bd0f73bf7f56c3d12c9.
- Apply starting HEAD: feat/complete-autonomy-authority-receipts-v1-20260913 at 7c29cf46d30f843c936dc04cf71ea984db83de57.
- Working Apply branch: feat/final-autoapply-loop-20260914. Resolve current HEAD via GitHub; this document is committed with the first source tranche.
- Hunter RC v2 is one commit ahead of its autonomy branch, preserving the guarded n8n routing repair.
- Apply anchor includes Teach hardening 83e4895076c511f40dc5b5d5ecc0e11d049612a0 plus six canonical authority/receipt commits.
- No Actions runs were returned for either exact starting source anchor. Older green runs are NOT evidence for these heads.
- No local checkout or local tests claimed; local dirty status not observed.

## This tranche

Block SUBMIT, GOVERNMENT_ID, and SMS semantic markers in both Teach capture and interaction recipe bindings. Existing PASSWORD/OTP/MFA/CAPTCHA/identity/authentication guards remain.
Add regression tests asserting forbidden mechanics cannot enter the lesson queue, be looked up, or become recipes.
Existing local SQLite capture, asynchronous drain, no-second-model-call, SHADOW/PROMOTED/rollback behavior is preserved.
Tests authored; executable evidence pending GitHub CI.

## Diagnosed implementation gaps

- autonomous_worker.execute always kills its browser in finally.
- CLI WorkerError handling reports FAILED_SAFELY / claimed_submission=false even when an error might occur after the final-submit agent starts.
- Agent at-most-once instruction is not itself durable exactly-once enforcement.
- Preparation prompt still emits NEEDS_INPUT for unresolved fields.
- Orchestrator retains required-task NEEDS_INPUT convergence.
- Teach async capture/worker and promotion/rollback already exist: reuse, do not rebuild.
- The complete UX and synthetic end-to-end flows have NOT been proven.

## Exact next task

Run CI on this isolated branch via a non-main PR after checking workflow safety. Inspect Hunter autonomous eligibility admission and worker wiring at the RC-v2 SHA; implement priorities 1–2 using existing targeting, Candidate Truth and Answer Vault. Then wire same-session reversible-control fallback to existing async Teach capture. Preserve one review-screen submit, add durable reconciliation before enabling any submit execution.

## Remaining acceptance

Background eligibility -> OPTIMIZING -> NEEDS REVIEW; issue isolation; automatic safe fallback; async trace learning; one review action; JIT authority; durable ambiguity/retry guard; independent receipts; Native/n8n synthetic E2E; migration/restart evidence; release package. No release-readiness claim yet.

## CI evidence for 7cc3a1e008b52ca7b6ae8d88d579ceefc4a4fb89

GitHub run 34803320925 native-host: 307 passed, 11 skipped, 2 warnings; Ruff passed. Repository safety passed. Extension stopped at Prettier on execution-request schema and this document. No local test result claimed. PR #24 targets the autonomy branch, not main. Other suites must be checked before release. Formatting-only follow-up preserves schema values.
