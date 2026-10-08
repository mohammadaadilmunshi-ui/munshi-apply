# MUNSHI: extension / initial dashboard parity

## Architecture

The initial Hunter Dashboard is the control plane. The hosted Apply database,
immutable application plan, durable prepare job, Netcup Chromium checkpoint,
frozen provider review, Hunter one-use submit mandate, and employer-proven
receipt are the ONE canonical lifecycle. Terminal commands are temporary
diagnostic controls, not a different execution system.

The Edge extension is a companion for watching that same run. Its old
tab-local AutoPilot is NOT proof of a hosted submission. When the operator
selects a hosted application ID, extension-local Start and Resume must be
disabled even if the read-only observer loses its connection.

## Changes in extension 0.2.12

- The AutoPilot view includes a live Netcup run inspector with application,
  session, plan, current checkpoint, durable preparation job, attempt budget,
  unresolved semantic control IDs, recent durable events, review count,
  submit command count, and stored employer receipt count.
- A new native messaging request observes the actual production Apply
  database through explicit owner-configured, host-key checked, read-only SSH.
  This cannot update the database, start a new application or click Submit.
- Raw answer values, applicant data, phone digits, passwords and event evidence
  payloads are not transmitted. The latest session is selected for observation;
  historical sessions from older plans do not falsely block the inspector.
  Tied latest session timestamps and unavailable monitoring remain blockers.
  This recency selection is informational and cannot authorize execution.
- Selecting a hosted identity disables the older independent local AutoPilot
  Start and Resume for that extension view. The hosted worker is unaffected.
- Local AI draft approval UI remains only for the old independent draft
  workflow. It does not authorize hosted Workday submission.

## Native observer configuration

After installing the new native host package in the existing owner-controlled
MUNSHI runtime, create an owner-only JSON config file at:

    ~/.config/munshi-apply/hosted-monitor.json

Example content (replace placeholders, do not include a private-key value):

    {
      "ssh_host": "YOUR_SSH_USER@YOUR_TRUSTED_NETCUP_HOST",
      "ssh_identity_file": "/absolute/path/to/your/ssh_private_key",
      "apply_container": "munshi-apply-production-apply-1"
    }

The config file must be chmod 0600. The private key itself stays in
macOS SSH storage; no credentials are copied into the extension. The
server must already be in the local SSH known_hosts. The inspector does not
configure or disable host-key checks.

For a reliable extension update, build from a CLEAN new source worktree.
Do not reset the user's dirty original source manifest or icon files.
Do not remove/reinstall the old Edge extension: its installed ID and storage
must be preserved. Back up the small compiled dist only; then copy the
verified new dist to the SAME unpacked extension path and use Reload in Edge.
Native messaging code needs its own independently verified installed update.

## One-approval policy

The user wants unattended autofill, page navigation and final submit after
the dashboard has granted its single approved execution mandate. The
extension must not ask for a second application-answer review or substitute
its own independent Submit click for that existing mandate. The canonical
Netcup submit worker claims its one-use authority and verifies provider
confirmation. Missing legally consequential answers, CAPTCHA, OTP, MFA, and
identity challenges are never guessed or bypassed.

## What remains

This source update is an OBSERVABILITY and anti-duplicate milestone, not a
working end-to-end production submission. There is no streamed Netcup
screenshot/video yet, no authenticated hosted Start/Pause/Resume command from
the extension, no Apply submit-worker activation and no new receipt.

Complete parity requires an authenticated owner-scoped backend run-control
API; signed, per-action browser events and masked screenshots visible in both
dashboard and extension; exact checkpoint/resume behavior; submit-worker
activation under the existing one-use authority; and a genuine Workday
submission receipt accepted by MUNSHI receipt verification.

## Test gates

Native read-only observer tests, extension UI regression tests, TypeScript
typecheck, ESLint, full Vitest, extension build, artifact verification, secret
scan, and a reviewed CI-green PR must pass before installed/native updates.
