# Hidden Edge Add-ons release

Status: preparation checklist. Submission and publication require separate owner authorization.

## What a hidden listing means

Microsoft Edge Add-ons is the official extension distribution catalog for Microsoft Edge. A hidden listing is not shown in normal catalog search or browsing; installation is limited to people who have its direct listing link. Hidden does not mean unreviewed, unlisted from Microsoft's systems, or exempt from store policy.

Microsoft currently documents developer registration and extension submission as free. Hosting, storage, email, observability, AI providers, and usage beyond free allowances are separate and can incur charges. No paid plan or billable add-on may be enabled for MUNSHI Apply without explicit owner approval.

## First hidden desktop submission

The hidden listing distributes the desktop Edge extension. Current Edge on iOS does not expose the general extension runtime required for MUNSHI's employer-page sensors, so the iPhone workflow is the authenticated hosted workspace rather than an iOS extension listing.

Do not make the first hidden submission until all of these are complete:

- browser-originated native health result from the reloaded desktop extension;
- private workspace deployment and owner-only sign-in boundary;
- privacy policy and support page on stable HTTPS URLs;
- accurate data-use disclosure covering résumés, protected facts, application content, device credentials, and diagnostics;
- permission rationale for broad HTTP/HTTPS page access, tabs, storage, Native Messaging on desktop, and any mobile-specific permission set;
- accessibility evidence on current Edge desktop and responsive-layout evidence for the hosted workspace on Edge on iOS;
- no secret, real résumé, profile, database, backup, diagnostic, or source map in either submission ZIP;
- a deliberate final-submission checkpoint remains enforced.

The listing must describe only verified desktop-extension features. It must not claim iPhone page injection or autofill. The separate hosted workspace description may accurately cover encrypted profile, résumé, review, device, and recovery functions after their release gates pass.

## Package set

Release operations produce:

- `munshi-apply-edge-vX.Y.Z.zip` for the desktop permission set;
- the private macOS native companion archive;
- release and migration manifests;
- SHA-256 checksums.

The store package is desktop-only. Do not add unsupported iOS-extension claims to the listing or package metadata.

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
6. Ask the owner for explicit authorization to upload the desktop package.
7. Submit as hidden with strictly accurate verified-feature wording and respond to Microsoft review.
8. Run the paired iPhone-workspace-to-desktop-extension handoff tests with synthetic data.
9. Complete encrypted sync, conflict, revocation, backup, and recovery tests before migrating real private data.
10. Ask separately before uploading an update, changing visibility, or publishing a replacement.
