# Workday + Universal Provider Proof V1

Status: design baseline started 2026-09-27  
Scope: provider-generic Workday hardening plus provider-neutral universal semantics.  
Non-goal: no employer-, requisition-, or job-specific selectors, values, or branching.

## Why this exists

The current runtime can already discover forms, classify many fields, upload the exact resume artifact, advance reversible pages, stop at security boundaries, and enforce exactly-once submit authority. The remaining problem is robustness: Workday uses controlled inputs, search-backed prompts, repeated experience/education groups, segmented phone controls, self-identification pages, legal attestations, and a review page that can expose silent autofill mistakes.

This design makes Workday an interaction recipe over a provider-neutral intent model. Candidate values stay in Candidate Truth / Answer Vault / protected resolvers. Workday code only knows how to interact with controls and verify the provider accepted the value.

## Invariants

1. No provider recipe may invent a candidate fact.
2. No provider recipe may infer protected/self-ID values from name, resume, location, language, or other proxy facts.
3. Optional fields with no canonical value remain blank.
4. Repeated employment/education values require an explicit repeat binding; semantic alias fallback alone may not cross-fill rows.
5. Every provider mutation is post-action verified. Visible text alone is not sufficient when provider validation says the field is invalid or uncommitted.
6. Prepare mode may click reversible navigation such as Save and Continue, but never the final employer submit boundary.
7. Review reconciliation must pass before one-use submit authority can be consumed.
8. A submitted or submission-unverified application is never resubmitted by a retry path.

## Universal field model

The universal layer should distinguish candidate meaning from provider mechanics.

### Core identity and contact

- HONORIFIC
- FIRST_NAME
- MIDDLE_NAME
- LAST_NAME
- PREFERRED_NAME
- EMAIL
- STREET_ADDRESS
- ADDRESS_LINE_2
- CITY
- STATE_PROVINCE
- POSTAL_CODE
- COUNTRY
- PHONE_DEVICE_TYPE
- PHONE_COUNTRY_CODE
- PHONE
- PHONE_EXTENSION
- LINKEDIN / GITHUB / PORTFOLIO / WEBSITE

PHONE_DEVICE_TYPE, PHONE_COUNTRY_CODE, PHONE, and PHONE_EXTENSION are separate intents. A phone number must never be reused as an extension.

### Eligibility and application questions

- PREVIOUS_EMPLOYEE
- PREVIOUS_APPLICATION
- AGE_18_PLUS
- WORK_LOCATION_ELIGIBILITY
- WORK_AUTHORIZATION_CURRENT
- SPONSORSHIP_CURRENT
- SPONSORSHIP_FUTURE
- IMMIGRATION_ASSISTANCE
- SALARY_EXPECTATION
- START_DATE
- NOTICE_PERIOD
- RELOCATION / TRAVEL / REMOTE / HYBRID / ONSITE

AGE_18_PLUS requires a user-confirmed eligibility fact or a secure derivation policy. WORK_LOCATION_ELIGIBILITY is protected because it may encode legal work eligibility. Salary answers require explicit approved answer memory; the system must not manufacture a number or phrase.

### Employment and education

Existing employment and education semantics remain, but execution must bind them to a repeat group and repeat index. The browser may detect “Work Experience 1”, “Work Experience 2”, “Education 1”, etc., but the resolver must bind rows to canonical profile entries before fill.

Optional provider fields such as employment location or field of study remain blank when Candidate Truth has no approved value.

### Voluntary disclosures and self-identification

- GENDER
- RACE_ETHNICITY
- HISPANIC_LATINO
- VETERAN_STATUS / PROTECTED_VETERAN_STATUS
- DISABILITY_STATUS
- EEO_SELF_ID

These are protected/self-ID domains. They may be filled only from explicit secure user choices. No provider-neutral heuristic may infer them.

The disability form also contains ordinary structural fields:
- SELF_ID_NAME: canonical legal full name
- SELF_ID_DATE: current execution date
- EMPLOYEE_ID: optional and blank unless explicitly known

### Legal attestations

LEGAL_ATTESTATION is distinct from a normal checkbox. A provider recipe may check a Terms and Conditions or certification box only when the execution mandate explicitly authorizes that attestation and the runtime binds the action to the exact visible terms/document identity. Otherwise it becomes a user-required task.

## Workday interaction recipe

Workday support must be based on component shape and provider metadata, not employer text.

### Search-backed prompt / combobox

For Workday prompt controls:
1. focus/click the control;
2. enter the canonical query;
3. wait for the popup/listbox identified by aria-controls / Workday data-automation-id;
4. require one exact normalized option match;
5. click or keyboard-select that exact option;
6. verify selected chip/token/backing provider state;
7. verify scanner satisfied=true and invalid=false.

Do not treat typed search text as a committed answer.

### Segmented phone

Treat the four possible components independently:
- device type;
- country phone code;
- phone number;
- extension.

Canonical phone normalization may render equivalent formatting variants, but may not change digits. Extension stays blank unless a distinct extension fact exists.

### Choice controls

Native selects, Workday custom select buttons, radio groups, and checkboxes use exact option matching followed by provider verification. Yes/No values should be normalized through a common boolean choice codec, not employer-specific text branches.

### Date controls

Use canonical dates and provider-required formatting. Verify the backing value after blur. Current-date attestations must be generated by policy, not copied from unrelated candidate dates.

### Repeated sections

Scanner output must include stable repeat-group metadata for Work Experience, Education, Certifications, Languages, Websites, and similar repeated containers. Provider execution binds each group to one canonical object and fills only that row.

### Page navigation

Workday prepare mode advances only reversible actions:
My Information -> My Experience -> Application Questions -> Voluntary Disclosures -> Self Identify -> Review.

The exact labels may vary. Detect navigation by action semantics and Workday component role, not by one employer's wording.

At Review, stop preparation and emit a canonical review snapshot. Never cross FINAL_SUBMIT during preparation.

## Review reconciliation gate

Before submit authority is issued, compare the provider Review page against the immutable plan and candidate truth.

Block if any of these occur:
- first/middle/last name duplication or recombination that differs from canonical legal-name parts;
- phone digits differ from canonical phone;
- phone extension is populated when no extension fact exists;
- address fields differ materially from canonical address;
- unexpected employment/education row count or cross-filled repeated fields;
- selected resume does not match the approved artifact SHA;
- a required normal field is unresolved;
- a protected/self-ID value was not supplied by its protected resolver;
- provider validation errors remain;
- review page differs from the frozen browser form digest after approval.

Protected/self-ID values in logs and evidence must be redacted or represented only by digests/policy metadata.

## Provider-neutral execution contract

The universal resolver emits a CanonicalFieldIntent:
- semantic_type
- sensitivity_class
- canonical value or secure resolver ref
- repeat binding when applicable
- allowed transformations
- verification requirements
- optional/required state
- provenance/truth binding

A provider recipe receives the intent and observed control, performs only mechanics, then returns:
- FILLED / SKIPPED_OPTIONAL / NEEDS_INPUT / FAILED
- interaction strategy
- provider verification evidence
- no candidate-value promotion back into canonical truth

This same contract must be usable by Workday, Greenhouse, Lever, Ashby, SmartRecruiters, and generic providers.

## Test matrix

Add an employer-neutral Workday fixture that models:
1. My Information: referral prompt, previous employee, country, legal name, address, segmented phone.
2. My Experience: two employment rows, two education rows, resume, websites.
3. Application Questions: location eligibility, age threshold, sponsorship, salary.
4. Voluntary Disclosures: protected self-ID choices plus legal terms attestation.
5. Self Identify: language, legal name, date, disability choice, optional employee ID.
6. Review: rendered summary followed by a final submit button.

Required regressions:
- phone device type cannot satisfy phone number;
- phone number cannot fill extension;
- country code is selected independently;
- search text is not considered a committed prompt value;
- repeated employment/education values cannot cross rows;
- optional unknown values stay blank;
- protected/self-ID values never come from normal semantic aliases;
- legal attestation requires mandate scope;
- review reconciliation catches duplicate middle-name/first-name composition;
- review reconciliation catches phantom phone extension;
- resume SHA remains exact;
- prepare reaches Review without clicking final submit;
- exactly-once submit behavior remains unchanged.

## Migration plan

1. Sync the current production Apply commit into GitHub so no production-only fixes are lost.
2. Branch the implementation from that exact commit.
3. Add/extend universal semantic types and classification tests.
4. Add Workday component interaction helpers and provider-neutral intent adapters.
5. Add repeat-binding and review-reconciliation tests.
6. Run unit + browser fixtures locally/CI.
7. Deploy behind the existing guarded Apply production path with submit authority off during image replacement.
8. Re-enable runtime after health/tests. One-use application authority remains separate.
9. Prove on a non-submit Workday preparation first; then continue the existing exactly-once submission flow only if the frozen review gate passes.
