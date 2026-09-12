# ApplyPilot Apply-Only Autonomous Worker Integration

This directory is the quarantine boundary for integrating the autonomous browser-execution pattern demonstrated by the public `Pickle-Pixel/ApplyPilot` project with MUNSHI Apply.

## Status

**Experimental only. No production or staging deployment. No live application submission from this branch.**

The upstream project is AGPL-3.0. Its source is intentionally **not copied into this proprietary repository**. The optional bootstrap script can check out the pinned upstream revision into the ignored local directory `integrations/applypilot/upstream/` for comparison and diagnostics.

Pinned upstream revision:

- Repository: `https://github.com/Pickle-Pixel/ApplyPilot.git`
- Commit: `4a8d521f67f5139811c0a910ef37410f8e6d836a`
- Upstream version observed: `0.3.0`

## Scope: apply only

MUNSHI already owns job discovery, opportunity scoring, Candidate Truth, résumé generation, cover letters, approved answers, application lifecycle, verification, and receipts. None of ApplyPilot's discovery/scoring/tailoring pipeline is being imported.

The only capability being added here is autonomous application execution:

```text
MUNSHI Job + Candidate Truth + tailored résumé + approved answers
  -> Application Plan V2
  -> deterministic MUNSHI execution where possible
  -> apply-only Claude Code + Playwright browser executor when needed
  -> MUNSHI independent verification
  -> receipt / CRM state
```

ApplyPilot's autonomous apply stage uses Claude Code as the reasoning agent and Playwright MCP for browser interaction. `bridge/autonomous_worker.py` is a MUNSHI-authored implementation of that execution pattern. It does not import ApplyPilot's answer policy, job database, discovery code, résumé tailoring code, or cover-letter code.

## Credentials

The MUNSHI Apply **Diagnostics → AI & Credentials Control Center** now has a separate Apply-only credential section.

Required for autonomous apply:

- Claude Code CLI installed locally;
- `npx` for Playwright MCP;
- Chrome, Edge, or Chromium;
- one Claude Code authentication method:
  - **Claude subscription login**: no Anthropic API key stored by MUNSHI; or
  - **Anthropic API key**: stored in macOS Keychain by the native companion.

Not required for this apply-only executor:

- Gemini API key;
- OpenAI API key;
- a second job-discovery API;
- a résumé-generation API.

An optional CapSolver credential can be stored separately in Keychain for future evaluation, but automatic challenge handling is disabled by default. The current worker returns `NEEDS_INPUT` for CAPTCHA, MFA, OTP, SSO approval, identity verification, and other authentication/security checkpoints.

Playwright and the browser do not require API keys.

## Authority and truth boundary

MUNSHI remains authoritative for candidate facts, work-authorization and sponsorship answers, approved Answer Vault values, selected artifacts and their SHA-256 digests, job identity, execution permissions, AI cost/turn budgets, lifecycle state, final verification, and receipt/CRM state.

The browser agent receives only the application package MUNSHI authorizes. It may not invent candidate facts or silently change protected answers.

Final submission requires **both** `permissions.final_submit=true` in the immutable MUNSHI execution request and `allowFinalSubmit=true` in local Autonomous Apply settings. If either authority is absent, the agent must stop before the irreversible submit action.

## Security checkpoints

The first implementation does not bypass security controls. It stops with `NEEDS_INPUT` for CAPTCHA/reCAPTCHA/hCaptcha/Turnstile/FunCaptcha, MFA, OTP, SSO approval, identity verification, bot/security challenge pages, or new consequential questions without an approved MUNSHI answer.

## Local bootstrap

The upstream checkout is optional and used only for source comparison/diagnostics:

```bash
bash integrations/applypilot/bootstrap-upstream.sh
```

It creates the ignored path `integrations/applypilot/upstream/`.

## Apply-only worker

Check prerequisites without opening an employer application:

```bash
python3 integrations/applypilot/bridge/autonomous_worker.py --diagnose
```

Validate the synthetic MUNSHI package without launching a browser:

```bash
python3 integrations/applypilot/bridge/autonomous_worker.py \
  integrations/applypilot/fixtures/synthetic-request.json
```

A real browser run remains gated while this branch is experimental. The worker consumes the MUNSHI application-execution request rather than an ApplyPilot SQLite job row.

## Cost controls

The worker uses a turn ceiling and a per-application dollar ceiling. The settings surface exposes browser-agent model, max turns, max AI cost, headless mode, final-submit authority, and Claude authentication mode.

The target architecture keeps deterministic MUNSHI controls and learned recipes first, using the paid autonomous agent for long-tail sites/widgets rather than paying for every field on every application.

## Integration files

```text
integrations/applypilot/
  README.md
  .gitignore
  UPSTREAM.lock.json
  bootstrap-upstream.sh
  bridge/
    mock_worker.py
    autonomous_worker.py
  contracts/
    application-execution-request.schema.json
    application-execution-result.schema.json
  fixtures/
    synthetic-request.json
```

All tracked bridge/contracts are MUNSHI-authored. No ApplyPilot implementation source is committed into this repository.
