# Hidden Edge Add-ons release

Status: preparation checklist. Submission and publication require separate owner authorization.

## What a hidden listing means

Microsoft Edge Add-ons is the official extension distribution catalog for Microsoft Edge. A hidden listing is not shown in normal catalog search or browsing; installation is limited to people who have its direct listing link. Hidden does not mean unreviewed, unlisted from Microsoft's systems, or exempt from store policy.

Microsoft currently documents developer registration and extension submission as free. Hosting, storage, email, observability, AI providers, and usage beyond free allowances are separate and can incur charges. No paid plan or billable add-on may be enabled for MUNSHI Apply without explicit owner approval.

## First hidden feasibility submission

Microsoft documents desktop sideloading, but the current public documentation does not provide an equivalent personal iOS unpacked-extension path. The first hidden submission may therefore be required to obtain the physical-iPhone installation evidence. Treat it as a feasibility candidate, not as the fully functional release.

Do not make the first hidden submission until all of these are complete:

- browser-originated native health result from the reloaded desktop extension;
- private workspace deployment and owner-only sign-in boundary;
- privacy policy and support page on stable HTTPS URLs;
- accurate data-use disclosure covering résumés, protected facts, application content, device credentials, and diagnostics;
- permission rationale for broad HTTP/HTTPS page access, tabs, storage, Native Messaging on desktop, and any mobile-specific permission set;
- accessibility and responsive-layout evidence on current Edge desktop and Edge on iOS;
- no secret, real résumé, profile, database, backup, diagnostic, or source map in either submission ZIP;
- a deliberate final-submission checkpoint remains enforced.

The feasibility listing must describe only the features already verified. It must not claim universal iPhone autofill, résumé synchronization, or full desktop parity.

After Microsoft makes the hidden candidate installable, complete every physical-iPhone gate in `MOBILE_AND_CROSS_DEVICE_ARCHITECTURE.md`, plus the authenticated D1/R2, pairing, revocation, recovery, and conflict tests. Only then prepare the fully functional hidden update.

## Package set

Release operations produce:

- `munshi-apply-edge-vX.Y.Z.zip` for the desktop permission set;
- `munshi-apply-edge-mobile-vX.Y.Z.zip` for the reduced mobile permission set;
- the private macOS native companion archive;
- release and migration manifests;
- SHA-256 checksums.

The store's accepted package strategy for one listing across desktop Edge and Edge on iOS must be confirmed in Partner Center before upload. Do not assume that a separate mobile ZIP can be attached to the same listing. If Microsoft requires one cross-platform manifest, consolidate only after physical testing proves the conditional runtime behavior and the permission review remains honest.

## Listing content

- Name: MUNSHI Apply
- Visibility: Hidden
- Category: Productivity
- Summary: Evidence-grounded application understanding, private pre-flight review, and verified preparation for legitimate job applications.
- Safety statement: MUNSHI pauses for CAPTCHA, MFA, OTP, identity verification, authentication, and final submission. It does not bypass security checks or invent protected facts.
- Support scope: latest generally available Microsoft Edge and, for mobile, latest generally available iOS after physical-device verification.

Required visual assets should show the real product state. Do not use a “Healthy” badge as proof of native or cloud connectivity; diagnostics must show extension, native companion, SQLite, and cloud status separately.

## Release procedure

1. Update the version consistently and generate clean desktop/mobile builds.
2. Run formatting, lint, type checking, TypeScript and Python tests, artifact validation, secret scanning, migration tests, and release packaging.
3. Inspect both ZIP manifests and file inventories; confirm no source maps or private files.
4. Install the exact ZIP candidate on a clean desktop Edge profile.
5. Record checksums, screenshots, privacy/support URLs, and the permission rationale.
6. Ask the owner for explicit authorization to upload the feasibility package.
7. Submit as hidden with strictly accurate foundation/feasibility wording and respond to Microsoft review.
8. Install the approved hidden candidate on the physical iPhone and run injection, storage, UI, cloud, file, navigation, background recovery, accessibility, and manual-checkpoint tests.
9. Complete encrypted sync, conflict, revocation, backup, and recovery tests before migrating real private data.
10. Ask separately before uploading a functional update, changing visibility, or publishing a replacement.
