# MUNSHI Apply — Legacy Cloud Sync Compatibility Repair

Date: 2026-08-15

## Symptom

The desktop Profile surface could remain in `Waiting to sync` and display:

`Cannot read properties of undefined (reading 'some')`

Both autosave-triggered synchronization and the manual `Sync now` path were affected because they share the same encrypted cloud snapshot reconstruction.

## Root cause

Profile synchronization reconstructs the encrypted cloud snapshot by reading the latest `PROFILE.V1`, `APPLICATION.V1`, review, and résumé events. Historical `APPLICATION.V1` payloads can predate additive `ApplicationPage` fields such as `navigationCandidates`. The application eligibility boundary assumed those arrays were always present at runtime and called `.some()`/`.filter()` directly.

As a result, a legacy application-history record could throw while the cloud snapshot was being reconstructed and block an otherwise valid profile synchronization.

## Repair

- Parse/decode `APPLICATION.V1` history through `ApplicationPageSchema.safeParse` before it enters application eligibility or the owner-visible application list.
- Additive schema fields receive their canonical defaults when possible.
- Genuinely malformed legacy application records are ignored for application reconstruction instead of aborting profile synchronization.
- Application eligibility now defensively treats missing runtime `questions`, `controls`, and `navigationCandidates` arrays as empty.
- Existing encrypted event history is preserved. No destructive cleanup or record deletion is performed.

## Regression coverage

- A valid legacy application snapshot that omits `navigationCandidates` is normalized successfully and remains eligible when its application evidence is otherwise sufficient.
- A malformed legacy application snapshot missing required controls is rejected from application reconstruction without throwing.
- A legacy non-application/help-page snapshot with missing newer arrays does not throw and remains ineligible.

## Verification

The guarded integration helper completed successfully before committing the clean repair:

- full root `npm run check`
- production extension build
- desktop/mobile artifact verification
- regression tests above

Temporary repair helper files self-removed before the clean implementation commit.
