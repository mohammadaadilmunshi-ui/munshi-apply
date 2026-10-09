# Crescent Energy R441: Six-stage readiness audit

Evidence: six user-provided manual Workday screenshots (NOT proof the hosted worker
reached those pages), read-only Netcup/Hunter checks, and synthetic browser tests.
No candidate answers, protected values, or confidential employer page text is
recorded here.

## Stage 1: My Information

- Referral: "How Did You Hear About Us?" displays a selected Indeed chip in
  the MANUAL screenshot. The automated plan matched one approved answer but
  returned WORKDAY_PROVIDER_PROMPT / FAILED_CLOSED. A browser regression
  reproduced false ambiguity from nested DOM option selectors; Apply now
  deduplicates one real actionable option while rejecting genuinely distinct
  duplicate options. The production cause needs one verified live retest.
- Phone: latest live preparation verified PHONE successfully.
- Phone extension: Candidate Truth includes an extension identical to the whole
  phone number. This is a bad profile fact, NOT a valid extension. Correct it in
  the owner dashboard; until then leave the optional field blank.
- Legal name: source first/middle parts overlap; compare the intended split with
  official identity documents, without guessing.
- Prior-employee status, country, address, email and phone country code:
  source facts exist, but each browser field needs provider verification.

## Stage 2: My Experience

- Manual screenshot shows two jobs and two education records; Candidate Truth
  has indexed work history and education facts. Do not invent missing work
  location, field of study, or additional entries.
- Workday school/degree prompts require a selected provider option.
- Resume must match the immutable approved Crescent artifact SHA-256, not merely
  the filename of a PDF displayed in a manual screenshot.
- Websites, certifications and languages only from approved facts.

## Stage 3: Application Questions

- Work eligibility, age, sponsorship and salary are shown in screenshots.
  Hunter has corresponding facts, but eligibility/sponsorship can be protected.
  Do not guess legal consequences or infer answers from nationality or visa.
- Salary is an available normal fact and must match the candidate's approved
  answer; browser acceptance still needs verification.

## Stage 4: Voluntary Disclosures

- Screenshot shows required gender, race/ethnicity, Hispanic/Latino, veteran and
  Terms controls. Required Hispanic/Latino is UNSELECTED in manual attempt; the
  next screenshot displays Workday's required-field validation error.
- Several self-ID answers exist only as opaque protected references. Storage
  alone is NOT permission to autofill. Use scoped authorized protected resolver.
- Terms checkbox requires the actual employer-specific legal attestation proof;
  do not automatically accept unrelated terms or make one up.

## Stage 5: Self Identify

- Required language, disability self-ID name, date and answer shown, plus
  optional employee ID. Name and date were empty in the manual screenshot.
- Use verified legal name, authorized execution-date policy, and existing
  approved protected preference; never infer disability status.

## Stage 6: Review & final Submit

- Provider Review must reconcile legal name, resume digest, phone/extension,
  work/education, all submitted answers, and scoped legal attestation; no
  validation errors or unresolved required fields.
- Final Submit requires existing one-use Hunter authority, dedicated Apply
  submit worker, employer-verified receipt. Hunter authority flags were off and
  submit-worker stopped at inspection. No final review or receipt yet.
- Last observed real employer automation remained on Workday first page with
  one REFERRAL pending task (checkpoint sequence 14). Do not equate manual
  screenshots or passing synthetic tests with live autonomous completion.

## Regressions and next safe step

- Six-page Chromium tests use both direct values and immutable plan-bound
  answers, including repeated jobs, education, protected choices, attestation
  and resume SHA verification, with no final Submit.
- New referral regressions cover nested duplicate selector matches, removable
  selected chip, truly distinct duplicate exact options (fail closed), and
  absent selected state (fail closed).
- On the next controlled live continuation, inspect value-free
  field_action_evidence.option_diagnostic and the following checkpoint. Do not
  erase durable records, regenerate resume, duplicate the employer application,
  or increase retry limits as a workaround for failed selector logic.
