# MUNSHI Apply — Universal Application Fill Audit

**Date:** 2026-08-16  
**Candidate:** 0.2.3  
**Scope:** browser application discovery, semantic classification, profile resolution, field interaction, verification, recovery, AI drafting, résumé handling, and guarded AutoPilot behavior.

## Executive verdict

The live Bain failures exposed a structural issue rather than a single site-specific selector bug. Generic labels such as `Start date` were being interpreted without their surrounding section, native month inputs were not normalized from full profile dates, employer taxonomies such as `Company Industry` and `Position Function` were not represented in the semantic model, and option matching did not have enough normalization for common ATS vocabularies.

Candidate 0.2.3 broadens the application engine at the model, scanner, resolver, interaction, profile, and test layers. The goal is not to hard-code Bain. The goal is to make MUNSHI capable of understanding and filling the major control families and application sections used across conventional browser-based ATS and employer career sites.

No browser extension can truthfully guarantee that it can fill every possible page. Closed shadow roots, inaccessible cross-origin frames, browser or operating-system file-picker security, CAPTCHA, MFA, OTP, identity verification, employer anti-automation controls, and genuinely novel widgets can prevent deterministic automation. MUNSHI therefore uses broad discovery and adaptive interaction while retaining explicit failure reporting and owner handoff for boundaries it cannot or should not cross.

## Root causes confirmed from the Bain physical run

### Section-blind dates

A bare `Start date` label was previously vulnerable to being confused with job-availability start date. On Bain Work History this could cause an employment start-date field to receive the owner's availability date instead of the employment record's start date.

The scanner is now section-aware. It supplies nearby headings and group context such as `Education History` or `Work History` to the semantic classifier. The semantic model now distinguishes:

- education start date
- graduation date
- employment start date
- employment end date
- application availability start date
- certification issue date
- certification expiration date

### Native month controls

Profile dates are stored as full dates when available. Many ATS forms use native month inputs. A stored value such as `2024-07-01` is now deterministically normalized to `2024-07` when the employer control is `input[type=month]`.

### Employer taxonomy selects

Bain asks for values such as `Automotive & Mobility` and `Human Capital` even though the profile may naturally contain `Automotive`, `Toyota Connected India`, `Human Resources`, `Recruiting`, or a detailed HR job title.

The option-normalization layer now understands common degree, field-of-study, state/territory, industry, and position-function vocabularies. Resolution can also derive a high-confidence employer taxonomy from authoritative profile evidence when an explicit taxonomy value has not been saved. The derivation remains bounded and conservative rather than inventing an answer.

### Repeatable records

Employment and education records are repeatable. Resolution now respects the repeated question index instead of always taking the first matching record. The same mechanism is available for certifications and languages.

### Profile coverage gaps

The extension Profile UI now exposes additional fields needed by real applications, including education start date, company industry, position function, employment type, current-employment state, security clearance, common disclosure answers, protected-veteran status, and EEO self-identification.

## Universal capability matrix

### 1. Page and application discovery

Supported discovery behavior includes:

- conventional `input`, `select`, `textarea`, and `button` controls
- ARIA buttons, comboboxes, checkboxes, switches, radio controls, and spinbuttons
- popup listbox, tree, grid, and dialog controls
- contenteditable fields
- open shadow DOM traversal
- all accessible frames through the extension content-runtime lifecycle
- dynamic rescanning after DOM mutations and navigation
- explicit application routes and known ATS context
- multi-step career registration flows
- application pages that initially contain weak or unclassified semantic labels
- application-state inference for personal data, education, experience, résumé, questions, EEO, disclosures, review, submission, and confirmation states

The scanner observes broadly, while the application eligibility gate continues to reject ordinary browsing pages that lack application evidence.

### 2. Identity and personal information

Semantic coverage includes:

- first name
- middle name or initial
- last name / surname
- preferred name
- full legal name
- pronouns

Protected identity values retain confirmation and review rules when required.

### 3. Contact information

Supported profile and semantic fields include:

- primary email
- alternate email in the profile vault
- phone / mobile / telephone
- LinkedIn URL
- portfolio URL
- website / personal website

Text, email, telephone, URL, and contenteditable controls are verified after interaction.

### 4. Address and location

Supported address fields include:

- street address
- address line 2 / apartment / unit
- city
- state / province / region
- postal / ZIP code
- country

Option normalization covers U.S. state abbreviations and full names, including common territories. This allows profile value `NJ` to match an employer option `New Jersey` while still preferring an exact employer option when one exists.

### 5. Education

Repeatable education records now support:

- school / university / institution
- degree / highest education level
- field of study / major / area of study
- education location
- education start date
- graduation or anticipated graduation date
- GPA

Degree normalization recognizes common specific-to-generic equivalence, such as `Master of Science` to an employer's `Master's Degree` option. Field-of-study normalization supports common HR, analytics, business, and computing vocabularies while preferring exact employer values before aliases.

If a school is genuinely absent from an employer's option list, MUNSHI does not fabricate a school match. A site-specific `School not listed` flow may require a subsequent rescan and explicit fallback interaction before a free-text school field becomes available.

### 6. Employment and work history

Repeatable employment records now support:

- employer / company name
- job title / position title
- employment location
- employment start date
- employment end date
- employment type
- currently employed state
- company industry
- position function / functional area
- responsibilities
- achievements as evidence for supported drafting

The resolver uses the repeated record index so separate employer blocks can resolve to separate profile records.

High-confidence employer taxonomy derivation is available when an explicit profile value is missing. Examples include automotive employers to `Automotive & Mobility` and HR/recruiting titles to `Human Capital`. Unrecognized employers or functions remain unresolved rather than being guessed.

### 7. Skills

Supported skills behavior includes:

- deterministic profile skill values
- native selects
- native multi-selects
- ARIA multi-selects
- custom popup selectors where a unique verified option exists
- line-, comma-, semicolon-, or JSON-array encoded multi-value inputs where supported by the interaction strategy

### 8. Certifications and licenses

Repeatable certification records support:

- certification / license name
- issuing organization
- issue date
- expiration date
- credential ID
- credential URL

Certification dates are semantically separated from education, employment, and application availability dates.

### 9. Languages

Repeatable language records support:

- language
- proficiency / fluency level

### 10. Work authorization and sponsorship

Supported protected semantics include:

- current work authorization
- current sponsorship requirement
- future sponsorship requirement
- immigration / visa assistance

These values remain protected. Broad field coverage does not remove the trust and confirmation rules around immigration-related answers.

### 11. Availability and work preferences

Supported fields include:

- earliest start date
- notice period
- full-time availability
- relocation willingness
- travel willingness
- remote preference
- hybrid preference
- onsite preference
- preferred work mode
- preferred locations

Availability start date is now a separate semantic type from employment and education dates, preventing the Bain Work History collision.

### 12. Compensation

Supported compensation handling includes:

- salary expectation
- deterministic yes/no acceptance where the saved owner preference explicitly supports it
- comparison to a stored minimum when the question clearly asks whether a stated salary is acceptable

MUNSHI does not invent compensation preferences.

### 13. Prior relationship and referral questions

Coverage includes:

- referral source
- previous employee
- previous application

The existing owner default for referral source remains bounded to its configured behavior.

### 14. EEO and voluntary demographics

Recognized protected semantics include:

- veteran status
- protected-veteran status
- disability status
- gender
- race / ethnicity
- EEO self-identification

These values remain protected and are not made less sensitive merely to increase fill rate.

### 15. Compliance and disclosure questions

Recognized protected semantics include:

- security clearance
- conflict of interest
- non-compete / restrictive covenant
- background-check acknowledgement
- drug-screening acknowledgement

The Profile UI now provides owner-controlled storage for these answers where appropriate.

### 16. Open-ended application questions

The semantic model recognizes common open-ended categories such as:

- why this company
- why this role
- role / responsibility understanding
- relevant experience
- career goals
- recruitment or sales motivation
- behavioral examples

The AI path remains evidence-grounded. It may use captured job-description context and confirmed profile, employment, project, education, and certification evidence. It must not invent employers, metrics, credentials, dates, immigration facts, or unsupported motives.

### 17. Native select controls

Single-select handling now follows an exact-first strategy:

1. exact employer value or label
2. normalized textual equivalent
3. bounded semantic alias
4. refusal when the result is absent or ambiguous

This prevents a broad alias from overriding a more precise employer option.

Supported normalization families include:

- states and territories
- countries where explicitly mapped
- months
- education levels and degrees
- common fields of study
- common company industries
- common job / position functions
- yes/no boolean variants

### 18. Native and custom date controls

Supported date interaction includes:

- `input[type=date]`
- `input[type=month]`
- `input[type=time]`
- `input[type=datetime-local]`
- `input[type=week]`
- date-like text inputs with deterministic format conversion
- ARIA / popup calendar controls where an exact date target can be verified

Failed date interactions restore the original value rather than leaving a partially changed field.

### 19. Radio, checkbox, and switch controls

Supported controls include:

- native radio groups
- native checkboxes
- ARIA radio controls
- ARIA checkboxes
- ARIA switches

Yes/no and boolean normalization is deterministic. Radio selection requires a unique matching option.

### 20. Comboboxes and dynamic popup controls

Supported behavior includes:

- controlled ARIA comboboxes
- portaled option lists
- open shadow-root option discovery
- popup listboxes
- popup trees
- popup grids
- exact-first option selection
- semantic alias fallback
- post-click verification
- restoration when verification fails

### 21. Multi-select controls

Supported behavior includes:

- native multi-selects
- ARIA multi-selects
- exact-first option matching
- deterministic aliases
- rollback if the requested final selection set cannot be verified

### 22. Text and long-answer controls

Supported controls include:

- text inputs
- search inputs
- email inputs
- telephone inputs
- number inputs
- textareas
- contenteditable controls

The fill layer respects read-only state, employer character limits, and native validity before considering a value successfully filled.

### 23. Résumé and file upload handling

The encrypted résumé vault supports:

- Master résumé classification
- Job / Niche Tailored résumé classification
- Imported résumé classification
- click-to-pick upload into the vault
- drag-and-drop upload into the vault
- current-application résumé selection
- reclassification
- removal from the active encrypted vault

Employer file inputs remain an owner-assisted browser / operating-system boundary. MUNSHI can request and verify the handoff, but it does not bypass browser file-selection security.

### 24. Dynamic application pages and recovery

The runtime includes:

- content-script liveness checks
- reinjection when the receiver is missing
- all-frame scan recovery
- navigation-aware page cleanup
- acknowledged page snapshots
- stale-control rebinding using field fingerprints and repeat metadata
- DOM stability waits
- post-interaction verification
- rollback on failed interactions where possible
- learned interaction recipes for supported custom controls

### 25. Validation and failure reporting

Recognized validation categories include:

- required
- format
- too long
- too short
- range
- pattern
- file type
- file size
- unknown employer validation

A field is not reported as filled merely because an event was dispatched. MUNSHI verifies the resulting control state.

### 26. AutoPilot safety boundaries

The broad-fill repair does not remove the existing guarded boundaries. Owner action remains required for:

- final employer submission
- CAPTCHA
- MFA
- OTP
- identity verification
- authentication checkpoints
- operating-system file selection

Unknown, ambiguous, unsupported, sensitive, or insufficiently grounded answers can remain unresolved or require review rather than being guessed.

## Regression coverage added for 0.2.3

New tests cover:

- Bain-style state select: `NJ` to `New Jersey`
- specific degree to generic employer degree option
- HR-focused interdisciplinary field of study to a supported HR option
- Work History full date to native month control
- company industry normalization
- position-function normalization
- section-aware Education History start date
- section-aware Work History start date
- section-aware Work History end date
- repeatable second employment record resolution
- Toyota employer identity to `Automotive & Mobility`
- HR role evidence to `Human Capital`
- education start-date resolution from an education record

Existing runtime, scanner, fill, semantic, resolver, AutoPilot, profile, security, migration, and owner-workspace tests continue to run alongside these additions.

## Physical Bain acceptance checklist

The physical browser run should verify all of the following on a fresh 0.2.3 build:

- application detected on the Bain registration flow
- State / Province filled from the saved profile
- highest education level filled
- school filled when a matching employer option exists
- field of study filled when a deterministic exact or mapped option exists
- education start date uses the education record, not availability
- graduation date uses the education record
- employer name uses the employment record
- job title uses the employment record
- employment start date uses the employment record
- employment end date uses the employment record
- company industry resolves or derives correctly
- position function resolves or derives correctly
- no field receives the earliest application-availability date unless the question is actually asking availability
- newly produced Edge runtime errors are inspected independently from historical errors

## Remaining truthful limits

The universal scanner and interaction engine is intentionally broad, but these cases may still require a new adapter, learned recipe, or owner handoff:

- closed shadow DOM
- inaccessible cross-origin frame contents
- canvas-only or graphics-only widgets
- controls that intentionally hide option values from the DOM until privileged interaction
- employer anti-bot systems
- CAPTCHA and related human-verification challenges
- MFA, OTP, and identity verification
- operating-system file-selection dialogs
- employer controls whose only valid answer requires information not present in the authoritative profile
- employer questions whose meaning is genuinely ambiguous
- unsupported `Other / not listed` flows that dynamically create a second field and need a separate rescan

These are treated as explicit boundaries, not silent successes.

## Release position

0.2.3 should be considered a broad universal-fill candidate, not final release, until the physical Bain run confirms the repaired scanner, semantic resolver, and fill interactions in Edge. PR #11 must remain draft and unmerged until that physical gate is satisfied.
