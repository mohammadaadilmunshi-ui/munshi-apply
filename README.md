# MUNSHI Apply

MUNSHI Apply is a local-first, evidence-grounded Microsoft Edge extension and native companion for understanding and preparing legitimate browser-based job applications.

The project is built around one compatibility rule: an unfamiliar application platform is mapped through the same discovery and semantic pipeline as a familiar one. Vendor-specific shortcuts may be added later, but they do not define support.

## Current milestone

Version `0.1.0` implements the Phase 0 engineering foundation and the first safe slices of Phases 1 and 2:

- a Manifest V3 Edge extension;
- a persistent side panel;
- an ephemeral service worker backed by an IndexedDB browser cache;
- generic DOM and ARIA control discovery across top-level pages and injectable frames;
- deterministic classification for common application questions;
- mandatory review flags for sensitive and consequential questions;
- a local Master Profile vault with protected facts;
- shared TypeScript contracts validated with Zod;
- a Python native companion with authoritative SQLite persistence, transactional outbox delivery, a health API, Native Messaging, and an optional signed n8n event bridge;
- private-runtime installation, verification, backup, update, rollback, and release-packaging operations;
- synthetic application fixtures, unit tests, CI, and security documentation.

This milestone is intentionally **observe only**. It does not fill fields, upload files, bypass security checkpoints, or submit applications.

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

Open a normal `http://` or `https://` application page and select the MUNSHI Apply toolbar action. The side panel will show the visible controls and the inferred question map.

To connect the local companion, copy the unpacked extension ID shown on `edge://extensions` and run:

```bash
./scripts/install.sh --extension-id <EDGE_EXTENSION_ID>
```

The macOS runtime defaults to `~/Library/Application Support/MUNSHI Apply/`; no private database, résumé, evidence, backup, diagnostic, or secret belongs in this repository.

## Configuration

No API key is required for the current milestone. Provider keys and n8n are deliberately optional. See [Configuration](docs/CONFIGURATION.md) before adding any secret.

## Safety boundary

MUNSHI Apply does not defeat CAPTCHA, MFA, OTP, identity verification, authentication protections, or anti-abuse systems. It pauses for user-controlled security checkpoints. It also does not change protected facts or high-risk answers without explicit user confirmation.

The complete design baseline is preserved in [Master Architecture](docs/MASTER_ARCHITECTURE.md).
