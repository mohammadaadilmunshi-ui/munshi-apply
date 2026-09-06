# Complete Application Loop V1 — Apply Forensic Baseline

Date: 2026-09-06

## Scope

Source-engineering-only consolidation for the MUNSHI Apply side of Candidate Truth -> Application Plan -> verified browser preparation -> Needs Input -> Final Review -> explicit Submit -> independently verified receipt.

No staging or production deployment is authorized by this branch.

## Verified Apply ancestry

- `chatgpt/resolution-orchestrator-usability` HEAD: `64a4762c569a696c1a723c9c6896765cad8b1e19`
- `feat/phase8-candidate-truth-consumer-v1` HEAD: `e955328bf4ebcafda591d57d3bb59ff4874d1eb6`
- Merge base: `ccde77f999c34ac7e61ba3c4b6b97dcc3f8cb989`

The resolution line carries the advanced browser/session/resolution architecture. The Phase 8 line carries the Hunter Candidate Truth read-only consumer and signed Career OS preparation-handoff foundation. Neither head alone contains the complete desired source foundation.

## Verified migration reconciliation

Both branches independently allocated migration number `012`:

- resolution line: `012_resolution_tasks.sql`
- Candidate Truth/handoff line: `012_career_os_preparation_handoffs.sql`

The integration keeps `012_resolution_tasks.sql` unchanged and renumbers the additive Career OS handoff migration to `013_career_os_preparation_handoffs.sql`. Migration-order tests are updated to require both. No historical production database is edited by this source change.

## Authority boundaries

- Hunter is the canonical Candidate Truth, application lifecycle, and CRM authority.
- Apply caches/consumes only a read-only Candidate Truth projection.
- Apply owns browser-observed ATS/session/execution evidence, checkpoints, and execution receipts.
- Local Apply values must never silently become canonical Candidate Truth.

## Submission invariants

`PREPARED != SUBMITTED`

`READY_TO_APPLY != SUBMITTED`

`HANDOFF_ACCEPTED != SUBMITTED`

`PLAN_ACCEPTED != SUBMITTED`

The existing signed handoff remains acceptance-only. Receiving and persisting a package or plan must never trigger browser execution or final submission by itself.

Final submit authority must remain disabled by default, require an explicit user command, and require independent post-action verification. CAPTCHA, MFA, credentials, and unsupported authentication flows fail closed or pause safely.

## Next implementation seam

After this consolidation is test-green, consume Hunter's immutable Application Plan V2 through a versioned signed transport envelope; persist/acknowledge it idempotently; create a checkpointed execution session that reuses current page scanning, field semantics, fill, navigation, interaction, and resolution architecture; build exact final-review approval; add default-off final submit; and return immutable correlated execution receipts to Hunter.

No live ATS, Gmail, OAuth, n8n, credential, staging, or production action is permitted in this tranche.
