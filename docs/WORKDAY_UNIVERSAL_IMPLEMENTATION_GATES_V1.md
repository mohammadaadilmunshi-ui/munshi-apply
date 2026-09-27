# Workday Universal Implementation Gates V1

Status: active implementation control  
Scope: all Workday applications and the provider-neutral MUNSHI Apply engine  
Important: this document is a release gate, not a job-specific runbook.

## Architecture boundary

MUNSHI must keep four concerns separate.

1. **Observation**
   - Scanner describes controls, prompts, navigation, repeat groups, validation state, and provider metadata.
   - Observation is value-free. It must not create candidate facts.

2. **Universal semantics and truth resolution**
   - Semantic engine identifies what a field means.
   - Hunter Universal Brain decides where an answer may come from.
   - Protected, self-identification, post-offer, credential, and legal-attestation values retain their stricter policy path.

3. **Provider mechanics**
   - Workday driver knows only how to make a Workday component accept a canonical value.
   - It cannot invent a value, reinterpret a candidate fact, or downgrade sensitivity.

4. **Review and exactly-once execution**
   - Provider Review output is reconciled with the immutable plan before one-use submit authority.
   - Prepare mode never crosses FINAL_SUBMIT.

A change is not Workday-proof unless all four layers agree.

## Gate 0 — production lineage

Before modifying the Workday executor:

- exact currently deployed Apply Git commit must be present in GitHub;
- exact SHA must descend from the last known GitHub Workday baseline;
- production-only commits must be inspected after sync;
- implementation branch must start from the exact production SHA;
- no implementation may be based only on an older GitHub branch if production has moved ahead.

The sync operation is Git-history-only. It must not checkout the working tree, deploy, start Docker, open a browser, or mutate an employer application.

## Gate 1 — universal semantic contract

The shared SemanticType contract must distinctly represent at least:

- PHONE_DEVICE_TYPE
- PHONE_COUNTRY_CODE
- PHONE
- PHONE_EXTENSION
- AGE_18_PLUS
- WORK_LOCATION_ELIGIBILITY
- HISPANIC_LATINO
- SELF_ID_NAME
- SELF_ID_DATE
- EMPLOYEE_ID
- LEGAL_ATTESTATION

Rules:

- generic phone wording must never swallow phone metadata;
- age threshold is protected eligibility data;
- work-location eligibility is protected;
- Hispanic/Latino is self-identification;
- employee ID is post-offer/optional unless explicitly present;
- legal attestation is not an ordinary boolean preference.

## Gate 2 — Hunter truth and sensitivity

Universal Brain must prove:

- structured legal-name facts outrank a derived split of full name;
- legacy full-name splitting is only a compatibility fallback;
- PHONE_EXTENSION has no fallback to PHONE;
- PHONE_COUNTRY_CODE has no fallback to PHONE;
- missing optional facts remain missing/blank;
- protected/self-ID values cannot be supplied through normal field-intelligence projection;
- browser semantic hints can raise sensitivity but never lower it;
- repeated employment and education facts remain entity-scoped.

## Gate 3 — Workday component mechanics

The Workday driver must support component classes, not employer selectors.

### Search-backed prompt
Typed search text is not a committed answer.

Required sequence:
1. focus/open;
2. type query;
3. bind popup/listbox through ARIA or Workday component metadata;
4. require exactly one normalized option match;
5. select exact option;
6. verify selected token/chip/backing provider state;
7. verify scanner satisfied=true and invalid=false.

### Segmented phone
Treat device type, country code, number, and extension independently.

### Choice controls
Native selects, custom Workday selectors, radio groups, and checkbox groups require exact choice matching plus post-action verification.

### Dates
Use canonical date values, provider formatting, blur, and backing-value verification.

### Repeated groups
Employment, education, certifications, languages, websites, and similar repeated containers require repeatGroupId + repeatIndex binding. No semantic-only cross-row fill.

## Gate 4 — page progression

Prepare mode may advance reversible navigation only.

Typical Workday sequence can include:

- personal/contact information;
- experience/education;
- application questions;
- voluntary disclosures;
- self-identification;
- review.

The labels may vary. State recognition must come from observed page semantics and navigation boundaries, not one tenant's text.

At Review:
- preparation stops;
- no final submit control is clicked;
- a review snapshot is produced.

## Gate 5 — review reconciliation

Before one-use submit authority, reconcile provider Review against immutable truth.

Block on:

- first/middle/last-name duplication or unexpected recomposition;
- phone digits mismatch;
- non-empty phone extension without a distinct extension fact;
- unexpected phone country-code mismatch;
- address mismatch;
- repeat-group row mismatch/cross-fill;
- missing required answer;
- provider validation error;
- wrong resume SHA;
- protected/self-ID answer without protected provenance;
- legal attestation without mandate-bound terms identity;
- unexpected change to the frozen browser form digest.

Protected/self-ID plaintext must not be emitted in diagnostic logs.

## Gate 6 — legal attestation

Terms/certification acceptance must be represented by a bound attestation object:

- semantic type LEGAL_ATTESTATION;
- visible label;
- terms URL when available;
- normalized terms/document fingerprint;
- provider page/form digest;
- execution-mandate scope;
- accepted timestamp.

The Workday driver may mechanically check the box only when this object is authorized. This remains part of the single-approval architecture; it must not create a second approval after the user already approved the exact package/mandate.

## Gate 7 — tests before deployment

Minimum local/exact-image proof:

1. semantic-engine unit tests;
2. scanner tests;
3. Hunter Universal Brain tests;
4. provider-neutral browser regression;
5. Workday six-page Chromium fixture;
6. repeat-group isolation tests;
7. search-backed prompt commit tests;
8. segmented-phone isolation tests;
9. review-reconciliation negative tests;
10. exactly-once submit regressions;
11. no-submit preparation fixture reaching Review;
12. regression suite for non-Workday providers.

A CI run that fails before executing steps is **not** a failing product test and is also **not** a passing signal. Record it as NO TEST EVIDENCE and use the exact-image/local test gate.

## Gate 8 — guarded production deployment

Deployment may temporarily stop the submit worker while replacing the Apply image.

After successful build, exact-image tests, health check, and runtime contract verification:

- restore submit runtime availability;
- do not issue application-specific one-use submit authority until Review reconciliation passes;
- user authorization and runtime ON/OFF remain separate concepts.

## Gate 9 — real Workday acceptance

First real acceptance after implementation:

1. verify no existing submit command/receipt for the bound application;
2. resume existing immutable plan/session when safe;
3. prepare to Review;
4. reconcile Review;
5. freeze review;
6. derive internal approval from the existing execution mandate where applicable;
7. issue exactly one submit authority;
8. consume once;
9. verify provider receipt;
10. if submission is unverified, reconcile only — never resubmit.

## Non-goals

Do not:

- hardcode one employer, tenant, requisition, source answer, candidate name, phone, demographic value, or salary;
- let Workday mechanics become a second answer brain;
- use AI to invent factual or protected answers;
- use a normal fill retry after a final submit command exists;
- assume visually populated text means provider-committed state.
