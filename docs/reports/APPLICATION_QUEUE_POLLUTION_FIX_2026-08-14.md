# Application Queue Pollution Fix — 2026-08-14

## User-visible symptom

The hosted owner workspace showed ordinary browsing pages as job applications, including the MUNSHI owner workspace itself, the public MUNSHI portfolio, and OpenAI Help Center pages. The overview also showed an inflated `answers to review` total.

## Root cause

The extension scanner intentionally observes interactive browser pages broadly, but the cloud publication boundary was equally broad. Whenever encrypted cloud sync was ready, every active `ApplicationPage` snapshot could be published as `APPLICATION.V1`, even when it was an ordinary documentation, portfolio, or workspace page.

The owner workspace then decrypted every latest `APPLICATION.V1` record and treated all of them as real application checkpoints. Its review counter summed every `requiresReview` question and did not subtract questions that had already been explicitly approved in a saved application review.

## Repair

### Desktop producer boundary

A deterministic application-eligibility classifier now gates cloud persistence. It requires real application evidence such as an explicit application context with multiple classified form questions, known-ATS application-specific questions, a résumé control inside application context, application-specific navigation with form questions, or the verified final-application boundary.

Ordinary help/documentation pages, portfolio pages, generic browsing pages, and candidate login pages without sufficient application evidence fail closed. The connected owner-workspace origin is always excluded even if its own UI contains application-like profile fields.

The same eligibility check is also applied when reading historical cloud application snapshots on desktop, so broad legacy observations no longer surface through the desktop cloud snapshot.

### Owner workspace compatibility filter

The hosted owner workspace independently applies the same conservative eligibility rules when decrypting legacy `APPLICATION.V1` history. This is intentionally non-destructive: old encrypted events remain encrypted history, but non-application snapshots no longer appear in the application queue or contribute to owner-facing review counts.

The owner workspace also excludes its own current origin explicitly.

### Review counter correctness

`answers to review` now counts only review-required questions on eligible application snapshots that do not already have an explicitly approved answer in the latest saved `APPLICATION.REVIEW.V1` record.

Application cards now show both total questions and pending-review count. Zero-question checkpoints are shown as tracked rather than presenting a misleading Review action.

## Guarded certification

The guarded repair workflow passed before producing the clean implementation commit:

- branch-diff integrity guard: passed
- Prettier: passed
- ESLint with zero warnings: passed
- TypeScript checks: passed
- root JavaScript/TypeScript tests: **200 passed across 36 files**
- production extension build: passed
- desktop/mobile extension artifact verification: passed
- repository secret scan: passed for the guarded tree
- owner workspace lint: passed
- owner workspace production build and Sites artifact validation: passed
- owner workspace tests: **11 passed**

New focused tests verify:

- OpenAI Help Center-style pages are rejected
- the public portfolio is rejected
- documentation about applying without an application form is rejected
- the owner workspace can never publish itself
- a real generic application form remains eligible
- a real Workday-style ATS application remains eligible
- a one-field candidate login is rejected
- résumé uploads are accepted only inside application context
- verified final-application boundaries remain eligible
- already-approved questions no longer count as pending review

Clean implementation commit:

`0f7996b068b5b29a5cf3aab70b1c7b5eeeadfdc5` — `fix: stop non-application queue pollution`

The temporary repair workflow and patch script self-removed after certification.

## Data and safety boundary

No historical encrypted cloud records were destructively deleted. The fix stops future pollution and hides legacy false-positive snapshots through deterministic compatibility filtering.

Final employer submission remains manual. CAPTCHA, MFA, OTP, authentication, identity verification, security checkpoints, and unsupported operating-system file selection remain owner actions.

## Deployment boundary

This report certifies repository source and automated owner-workspace build behavior. It does not by itself prove that the already-open `chatgpt.site` deployment has refreshed to this exact source revision. The hosted UI should be reloaded/redeployed through its existing hosting path before claiming the screenshots are physically corrected on the iPhone.

PR #11 remains draft and unmerged. No merge authorization is implied by this repair.
