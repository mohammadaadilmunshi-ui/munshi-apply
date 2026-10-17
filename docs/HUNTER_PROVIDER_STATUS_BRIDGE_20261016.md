# MUNSHI Apply and Hunter provider status bridge

Updated: October 16, 2026. Development-only and read-only. The original Hunter dashboard remains the source of truth.

## Integration ownership

Hunter's authenticated /api/application-provider-status/by-application/{application_id} endpoint returns a small tenant-scoped status projection and never modifies an application.

Apply owner cloud exposes /api/hunter-status?applicationId=... to authenticated paired-workspace devices. It requires an exact approved workspace ID, HTTPS Hunter hostname and server-only scoped Hunter status credential. The credential is never sent to the extension.

Extension AutoPilot and Diagnostics display status only when an exact existing application ID matches. Provider-reported submission and independently confirmed employer receipt have different labels. Missing matches and unavailable transport are not treated as success.

## Server-only Cloudflare environment

- MUNSHI_HUNTER_BRIDGE_WORKSPACE_ID: exact permitted owner-workspace ID.
- MUNSHI_HUNTER_BRIDGE_SECRET: a restricted Hunter API secret; never a public environment variable.
- MUNSHI_HUNTER_STATUS_ORIGIN: approved HTTPS backend host exactly dashboard.munshi.systems.

Absent or wrong values return errors without contacting Hunter. The currently protected dashboard HTTPS frontend may return HTTP 401 to a cloud worker. DO NOT disable dashboard Basic Auth to make this work. Establish and verify a separate protected server-to-server route before enabling the bridge.

## Source and tests

Backend: apps/owner-workspace/app/api/hunter-status/route.ts and bridge.ts.
Extension: apps/extension/src/storage/hunter-provider-status.ts and sidepanel/App.tsx.
Contract tests: apps/owner-workspace/tests/hunter-status-bridge.test.mjs and apps/extension/src/storage/hunter-provider-status.test.ts.

Checks:

- npm ci --ignore-scripts --no-audit --no-fund
- npx vitest run apps/extension/src/storage/hunter-provider-status.test.ts
- node --test apps/owner-workspace/tests/hunter-status-bridge.test.mjs
- npm run typecheck --workspace @munshi-apply/extension
- npm run build --workspace @munshi-apply/extension
- independently install the owner-workspace lockfile and run its TypeScript and deployment build.

This change is not a license to upload profiles, retry applications, submit applications or bypass employer protection. The release-aligned worktree is based on the actual version 0.2.12 branch and preserves the hosted-run inspector. Before replacing the installed extension, prove the exact browser installation and native host version agree with the release artifact.

## Deployment blockers

The owner-workspace server route and HTTPS transport are not configured or staged. Hunter PRs #103 and #104 need reconciled staging validation and migrations 058/059; Netcup OAuth needs authorized user consent and a working protected callback. The Native browser worker must demonstrate full Prepare to Review and correct PDF, and an independently confirmed employer receipt is still unproven.

DO NOT describe this bridge as a completed production auto-apply system.

## Scoped original-dashboard ingress design

The server-only Cloudflare credential is **MUNSHI_HUNTER_STATUS_BRIDGE_SECRET**
on the Hunter side, unrelated to HUNTER_API_SECRET. The sole Hunter endpoint
it can authorize is the exact read-only GET
/api/application-provider-status/by-application/{application_id}.
The Apply workspace forwards it using X-Munshi-Status-Bridge-Secret.

An audited original-dashboard Caddy route must permit only that GET path family
and forward it to Hunter FastAPI while leaving Basic Auth on the rest of
dashboard.munshi.systems. Requests without the bridge secret fail at HTTP 401.
Never send the general Hunter API token to Cloudflare or the extension.

## Production-aligned 0.2.12 merge

The status bridge was cherry-picked onto the current production-aligned
sync/production-41b602f-20260927 branch (baseline c9a5214), not the older
0.2.11 security branch. The merge retained HostedRunInspector and wired the
new provider state panel alongside it. Full npm run check passed on the
release-aligned source (650 unit tests, typecheck, build, artifact and secret
scan), plus owner workspace TypeScript, five bridge contract tests, nine
deployment-contract tests and staging transport static guard.

The original dashboard stays the only user-facing release destination.
