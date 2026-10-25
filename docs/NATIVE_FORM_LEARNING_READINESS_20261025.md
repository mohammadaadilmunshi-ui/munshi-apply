# MUNSHI Native: evidence-to-independence release gate

Status: **local implementation tested; browser CI, staging, and live authority pending**.
The code in this feature branch must not be described as deployed or as an
independently verified production submitter until those gates pass.

## What a learning observation means

Keep six evidence types separate:

1. External provider claim or application status: discovery only, never proof of
   MUNSHI Native browser capability or an employer submission receipt.
2. External field/review observation: structural research evidence. Do not import
   another service's answer values or assume its form submission is reproducible.
3. Native browser action attempt: ATS, semantic/control kind, strategy, opaque
   field fingerprint, and status only; no applicant answer, label, selector, or
   credential.
4. Native post-action DOM scan: independent verification that the field was
   committed, not just a successful click or JavaScript return value.
5. Cross-application hypothesis: at least three **distinct canonical
   application IDs**, all post-scan verified, no recorded unverified attempt for
   the pattern. Replacement plans, retries, or repeated lessons on one
   application cannot manufacture independent evidence.
6. Held-out Native replay and employer receipt: separate proof; neither can be
   inferred from a hypothesis, vendor status, or a generic success page.

Native's new read-only `GET /v1/native-learning/snapshot` uses the existing
authenticated owner scope and includes a value-free `held_out_self_test_queue`.
It does **not** expose application IDs, answers, raw questions, or URLs, and
cannot promote a recipe or authorize submission. The previously audited
external count (3,697 observations) is historical evidence, not 3,697 native
submissions or learned executable rules.

## Deterministic checks on the exact release source

Run the ordinary test/build/secret scan workflow in CI (see `.github/workflows/ci.yml`)
and the Chromium fixture workflow (`.github/workflows/browser-tests.yml`).
The latter explicitly tests `MUNSHI_RUN_BROWSER_TESTS=1` with a real browser.

Additional high-risk invariants:

- Test `test_native_form_learning_v1.py`,
  `test_interaction_recipe_service.py`, `test_account_teach_service.py`,
  `test_complete_application_loop.py`, and the account/unknown-provider
  integration tests.
- Assert repeated sessions/versions of one application stay `SHADOW`.
- Assert three verified independent applications may advance a _mechanics_
  recipe only; form telemetry remains `SHADOW_ONLY` until held-out replay.
- Assert a verified failure quarantines/rolls back the proper recipe and never
  causes an automatic repeat of a final employer submit.
- Assert all employer submits still require immutable final review, one-use
  command authority, exact-job binding, and independently verified receipt.
- Assert protected/self-ID, password, MFA, OTP, CAPTCHA, and legal attestation
  are neither learned as unrestricted answers nor bypassed.
- Verify the user's current start-date/authorization facts from Candidate Truth;
  do not infer or change them from any external provider observation.

## Staging self-test sequence (no real employer submission)

1. Confirm exact source SHA, CI tests, container-image digest, unchanged
   production data volumes, and working rollback to the prior Apply image.
2. Use isolated synthetic Greenhouse-like and Workday-like fixtures with known
   expected controls, uploads, multi-page movement, and intentional failures.
   Add BrassRing, Dayforce, SAP SuccessFactors, SmartRecruiters and other ATS
   fixtures as legal demonstrator pages/evidence become available. Prioritize
   actual unverified Native controls and external _form_ evidence, not status
   totals or public provider marketing claims.
3. Compare predicted semantic/control matches against independent expected
   fields; capture exact strategy, separate verification result, failure reason,
   checkpoint identity and retry identity. Keep all actions value-free in
   learning telemetry. Re-run with held-out pages not used to formulate the
   hypothesis. A synthetic completion is not an employer receipt.
4. For account creation/verification, exercise a controlled mailbox identity,
   one-time artifact correlation, same-session continuation, expiry, fallback,
   and human checkpoint handling. No CAPTCHA/MFA circumvention.
5. Reconcile the staging `native-learning/snapshot` against event rows under
   the same owner. Confirm that identical plan retries do not change distinct
   application counts; cross-owner observations and provider statuses do not
   change Native proof or receipt counts.
6. Test unknown-field pause -> owner answer -> signed replacement plan -> same
   checkpoint resume, without fabricating responses or creating a new job ID.
7. Only after the staging suite and one controlled non-submitting real-browser
   canary pass should a separate, explicitly authorized exact-job live submit
   canary be considered. Use the frozen review, one-use submit, and independent
   receipt reconciliation gates. Ambiguity stops; do not blindly retry.

## Release and promotion decision

This work is based on Apply production source `c00fc411fb8efd6f928d2777a99c2402c89099bf`.
Keep a dedicated review branch and PR. Do not force-push main, mix Hunter/Apply
database migrations into a code-only release, modify production credentials,
or switch on a submit worker as part of learning collection. Preserve the
original dashboard and its history. Publish only after repository write
permission is granted; then run CI, isolated Netcup staging, and exact-image
release validation before any production promotion.

### Next Native engineering priorities after this release

1. Collect verified form actions from safe prepare sessions, including control
   kinds and failure traces, on more than one employer per ATS.
2. Build held-out fixture replays for the high-evidence, failure-prone control
   families; do not encode employer-specific credentials or brittle selectors.
3. Record replay success/failure separately from observational confidence,
   with rollback on regressions and provider-version drift.
4. Improve the native account-mail-continuation chain, unresolved-question
   handling, immutable resume/artifact reuse, and final receipt correlation.
5. Promote non-sensitive, reversible mechanics only when validation passes;
   never promote vendor status evidence into native submission permission.
