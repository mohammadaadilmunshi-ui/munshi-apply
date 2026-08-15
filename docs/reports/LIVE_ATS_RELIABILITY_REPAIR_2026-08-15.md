# Live ATS reliability repair — 2026-08-15

## Scope

This report records the live Levin application failures that were not reproduced by the original synthetic/browser suite, together with the corrective changes made on `feat/v3-foundation-alignment`.

## First live failure set

The initial physical Edge smoke test exposed several independent defects:

- passive or ancestor-hidden reCAPTCHA integration could be mistaken for an active CAPTCHA checkpoint;
- an unpacked-extension reload could leave an already-open employer tab without a current content-script receiver;
- continuously mutating ATS DOM could starve the post-fill snapshot until AutoPilot timed out;
- required-marker labels such as `First Name *`, `Last Name *`, and `Preferred Pronouns *` were not normalized consistently;
- confirmed ordinary protected profile facts were over-gated;
- preferred pronouns were missing from the semantic/profile surface;
- hosted deterministic profile lookup lagged desktop mappings.

The first repair hardened content-runtime recovery, forced serialized post-action snapshots with a bounded mutation debounce, normalized required labels, added pronouns, aligned hosted profile lookup, and distinguished passive/invisible CAPTCHA integration from an actual visible challenge.

## Second live failure set

A subsequent Levin run showed that MUNSHI could fill the basic identity/contact fields but still required the owner to complete most of the later application manually. The same run also exposed a durable checkpoint acknowledgement failure.

### Semantic coverage gaps

The live form used wording that was outside the deterministic ontology, including:

- `Are you available to start on September 29, 2026?`
- `When are you available to start this role?`
- `Would this be your first experience working in a professional recruitment role?`
- `Would you require any Visa sponsorship now or in the future ...?`
- `How would you describe 360° recruitment and what are the key responsibilities of the position?`
- `What motivates you to pursue a career in recruitment or sales?`

The semantic engine now recognizes those question families without inventing answers.

### Deterministic answer-resolution gaps

The resolver now:

- derives a yes/no answer to a dated availability question by comparing the requested date with the explicitly saved `earliest_start_date`;
- continues to return the exact saved date for ordinary `When are you available to start?` fields;
- can answer that a recruitment role is not the applicant's first only when authoritative, explicitly usable prior recruitment evidence exists in the employment profile;
- leaves that question unresolved when prior recruitment evidence is absent rather than assuming an answer;
- permits explicitly confirmed authoritative work-authorization/sponsorship facts to become deterministic `READY` answers while unconfirmed protected facts remain review-gated;
- preserves the AI/review boundary for open-ended written answers.

### Checkpoint acknowledgement mismatch

The browser creates checkpoint timestamps with JavaScript `Date.toISOString()`, which emits UTC RFC3339 text with millisecond precision and a `Z` suffix. The Python native host parsed that timestamp into a `datetime` and serialized it back using Pydantic's default representation. The two timestamp strings could therefore represent the same instant while failing the browser's exact checkpoint acknowledgement comparison.

`ApplicationCheckpointPayload.wire_payload()` now canonicalizes `createdAt` to the same UTC millisecond `Z` format used by the extension. Regression coverage verifies that save acknowledgements and subsequent reads preserve the exact canonical wire value.

## Deliberate remaining owner/review boundaries

This repair does not guess contextual answers that are not grounded in the profile. Examples include site-specific location/proximity commitments, compensation acceptance choices, and employer-specific multi-select personality/experience statements when no explicit reusable fact or derivation exists.

Open-ended prompts such as role understanding and career motivation are now classified into the existing AI-safe draft categories, but generated text still requires the configured AI/provider path and owner review. Final submission, CAPTCHA, MFA, OTP, identity verification, authentication, and operating-system file selection remain owner actions.

A résumé hash mismatch also remains fail-closed by design: MUNSHI does not silently treat a different local file as the immutable résumé version already bound to an application.

## Verification

Final reviewed branch head for this repair: `253a4aabd7d9ca259e20adbac909b458c6e3c139`.

All normal pull-request workflows passed at that head:

- CI — success
- Browser tests — success
- Security — success
- Migration tests — success
- Owner workspace — success

The final extension CI passed formatting, ESLint, workspace TypeScript checks, **39 test files / 241 tests**, production build, desktop/mobile artifact verification, repository secret scanning, and repository safety. The native-host job also passed Ruff and Pytest, including the checkpoint wire-format regression.

Fresh unpacked Edge artifact from the final CI run:

- name: `munshi-apply-edge-unpacked`
- artifact ID: `9243892835`
- SHA-256: `7c928ec9024b7442f2e48e0609a8bc5d857a676473f8c5e7b813fc01560bd8df`

The draft pull request remains open and unmerged.
