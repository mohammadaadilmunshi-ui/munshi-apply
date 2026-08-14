# MUNSHI Apply

MUNSHI Apply is a local-first, evidence-grounded Microsoft Edge extension and native companion for understanding and preparing legitimate browser-based job applications.

The project is built around one compatibility rule: an unfamiliar application platform is mapped through the same discovery and semantic pipeline as a familiar one. Vendor-specific shortcuts may be added later, but they do not define support.

## Current milestone

Version `0.2.0` adds the first end-to-end encrypted, cross-device workflow to the Phase 0 foundation:

- a Manifest V3 Edge extension;
- a persistent side panel;
- an ephemeral service worker backed by an IndexedDB browser cache;
- generic DOM and ARIA control discovery across top-level pages, injectable frames, and open Shadow DOM;
- deterministic classification for common application questions;
- mandatory review flags for sensitive and consequential questions;
- a local Master Profile vault with protected facts;
- owner-held AES-256-GCM encryption for synchronized profile facts, résumés, application checkpoints, and reviews;
- short-lived device pairing, revocation, and recovery-key workflows;
- a hosted iPhone workspace that remains available while the Mac is off;
- per-application answer approval and résumé selection synchronized between iPhone and desktop;
- guarded filling of approved native controls with post-action DOM verification;
- shared TypeScript contracts validated with Zod;
- a Python native companion with authoritative SQLite persistence, transactional outbox delivery, a health API, Native Messaging, and an optional signed n8n event bridge;
- private-runtime installation, verification, backup, update, rollback, and release-packaging operations;
- synthetic application fixtures, unit tests, CI, and security documentation.

This milestone fills only explicitly approved, supported controls. File-picker selection, CAPTCHA, MFA, OTP, identity verification, and final submission remain deliberate manual checkpoints. Unsupported custom widgets remain manual.

## Repository map

```text
apps/extension        Edge extension and side panel
apps/native-host      Local Python companion and n8n bridge
packages/contracts    Cross-runtime domain contracts
packages/semantic-engine
packages/application-model
packages/shared
tests/synthetic-sites Universal scanner fixtures
migrations            Numbered SQLite migrations
docs                  Product, architecture, security, and decisions
```

## Local verification

Requirements: Node.js 22 or newer, npm 11, and Python 3.12.

```bash
npm install
npm run check

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './apps/native-host[dev]'
ruff check apps/native-host
pytest apps/native-host
```

## Load in Microsoft Edge

```bash
npm run build
```

Then open `edge://extensions`, enable **Developer mode**, choose **Load unpacked**, and select:

```text
apps/extension/dist
```

The iPhone experience is the authenticated hosted workspace. Current Edge on iOS does not expose the general desktop-extension runtime needed for page injection, so employer-page discovery and guarded filling run on a paired desktop Edge installation. The phone remains fully useful for profile and résumé management, application review, answer approval, device management, and recovery while the Mac is off. See [Mobile and cross-device architecture](docs/MOBILE_AND_CROSS_DEVICE_ARCHITECTURE.md).

Open a normal `http://` or `https://` application page and select the MUNSHI Apply toolbar action. The side panel shows discovered controls, inferred questions, synchronized approvals, and the guarded fill action.

To connect the local companion, copy the unpacked extension ID shown on `edge://extensions` and run:

```bash
./scripts/install.sh --extension-id <EDGE_EXTENSION_ID>
```

The macOS runtime defaults to `~/Library/Application Support/MUNSHI Apply/`; no private database, résumé, evidence, backup, diagnostic, or secret belongs in this repository.

## Configuration

No API key is required for the current milestone. Provider keys and n8n are deliberately optional. See [Configuration](docs/CONFIGURATION.md) before adding any secret.

No chargeable cloud, storage, AI, email, observability, or distribution option may be enabled without explicit owner approval. The planned private cloud workspace begins on available free allowances and must warn before any paid upgrade is required.

## Safety boundary

MUNSHI Apply does not defeat CAPTCHA, MFA, OTP, identity verification, authentication protections, or anti-abuse systems. It pauses for user-controlled security checkpoints. It also does not change protected facts or high-risk answers without explicit user confirmation.

The complete design baseline is preserved in [Master Architecture](docs/MASTER_ARCHITECTURE.md).

Private distribution preparation is tracked in [Hidden Edge Add-ons release](docs/EDGE_ADDONS_HIDDEN_RELEASE.md). The first listing will remain hidden; package upload or publication requires separate authorization.
