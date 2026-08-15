# Résumé vault synchronized deletion — 2026-08-15

## Scope

The owner workspace résumé vault now supports explicit deletion of an uploaded encrypted résumé from each résumé card.

## Behavior

- Each résumé card exposes `Download` and `Delete` actions.
- Deletion requires an owner confirmation prompt before any destructive action occurs.
- The object deletion endpoint is owner-only and refuses non-résumé encrypted objects.
- Confirmed deletion removes the encrypted résumé bytes from R2 and removes the corresponding encrypted-object metadata row from D1.
- The owner client then publishes an encrypted `RESUME.V1` tombstone carrying `deletedAt` so paired clients learn that the résumé was deleted.
- The Edge extension excludes tombstoned résumés from the active résumé snapshot and preserves version history when later résumé versions are uploaded.
- Existing application records may continue to reference the historical résumé identity; deletion does not rewrite historical application evidence.

## Verification

The implementation was published in commit `30e7ce401c1477a8b3999025ac408b4e1e1ff518` after the dedicated repair gate passed:

- root formatting, lint, type checks, tests, production build, artifact verification, and secret scan;
- owner-workspace clean install, lint, tests, and production build;
- focused regression coverage for the résumé deletion request path.

The draft PR remains open and unmerged. This documentation commit exists to trigger the normal pull-request workflow suite against the final source state.