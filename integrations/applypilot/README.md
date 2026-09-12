# ApplyPilot Autonomous Worker Integration

This directory is the quarantine boundary for evaluating and integrating the autonomous browser-execution ideas from the public `Pickle-Pixel/ApplyPilot` project with MUNSHI Apply.

## Status

**Experimental only. No production or staging deployment. No live application submission.**

The upstream project is AGPL-3.0. Its source is intentionally **not copied into this proprietary repository**. Instead, the bootstrap script checks out the pinned upstream revision into the ignored local directory `integrations/applypilot/upstream/` for evaluation.

Pinned upstream revision:

- Repository: `https://github.com/Pickle-Pixel/ApplyPilot.git`
- Commit: `4a8d521f67f5139811c0a910ef37410f8e6d836a`
- Upstream version observed: `0.3.0`

## Purpose

This integration is intended to test an autonomous execution layer behind MUNSHI's existing governed application pipeline:

```text
Candidate Truth
  -> Opportunity / Job
  -> Resume V5
  -> Application Plan V2
  -> MUNSHI deterministic execution
  -> autonomous-worker fallback when needed
  -> independent MUNSHI verification
  -> receipt / CRM state
```

MUNSHI remains authoritative for candidate facts, approved answers, document versions, job identity, execution permissions, state transitions, final verification, receipts, and audit history.

## Safety and trust boundary

The worker must not become the source of truth for candidate data or submission success.

For the first integration milestone:

- no production/staging mutation;
- no live credentials;
- no real job applications;
- no live final submission;
- no CAPTCHA bypass integration;
- no MFA, OTP, identity-verification, or authentication circumvention;
- no raw secrets in prompts or logs;
- no autonomous invention of candidate facts;
- no direct write access to MUNSHI's authoritative database;
- no weakening of existing Application Plan, review, or verification rules.

A worker may propose or execute only actions explicitly allowed by a MUNSHI execution contract. MUNSHI independently verifies the observable result.

## Local bootstrap

From the repository root:

```bash
bash integrations/applypilot/bootstrap-upstream.sh
```

This creates a detached checkout under:

```text
integrations/applypilot/upstream/
```

That directory is intentionally ignored by Git.

## Integration files

```text
integrations/applypilot/
  README.md
  .gitignore
  UPSTREAM.lock.json
  bootstrap-upstream.sh
  contracts/
    application-execution-request.schema.json
    application-execution-result.schema.json
```

The contract files are MUNSHI-authored clean-room interfaces. They do not copy ApplyPilot implementation code.

## Planned proof sequence

1. Bootstrap the pinned upstream code locally.
2. Run read-only/static diagnostics and upstream tests where available.
3. Build a mock-only bridge from a synthetic MUNSHI Application Plan into the autonomous worker.
4. Exercise synthetic application fixtures only.
5. Capture event traces, estimated model usage, execution time, and failure classes.
6. Require independent MUNSHI verification for every claimed success.
7. Compare deterministic execution versus autonomous fallback.
8. Only after evidence is strong, design an owner-approved path for guarded real-world trials.

## Cost objective

The autonomous AI path should be an escalation layer, not the default for every field. Known controls and learned recipes should remain deterministic so paid model usage trends downward over time.
