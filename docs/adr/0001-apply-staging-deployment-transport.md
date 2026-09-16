# ADR 0001: Apply-specific Netcup staging deployment transport

Status: Proposed

Date: 2026-09-16

## Context

MUNSHI Apply has a Docker staging runtime, but the repository did not have an Apply-specific authenticated GitHub-to-Netcup transport or a source-controlled bootstrap for that transport. Hunter already established an exact-SHA Git-bundle deployment pattern after a prior production/staging incident, but reusing Hunter's deployment command/key directly would give Apply deployment automation unnecessary authority over Hunter and production.

The Apply transport must support controlled staging proof without weakening the existing one-review, truth-safety, exactly-once, receipt, or final-submit gates. Normal source deployment must never itself grant submission authority.

## Decision

Use a separate Apply staging transport with these boundaries:

1. Deployment is manual-only through `workflow_dispatch` and requires an exact 40-character Git SHA plus the source branch that contains it.
2. GitHub Actions proves branch ancestry, runs the Apply test suite and transport guard, builds the staging image, and sends a verified Git bundle to Netcup. Netcup does not fetch source from GitHub during deployment.
3. A dedicated ed25519 GitHub Actions key is stored only as a protected GitHub staging secret. Its server-side public key is restricted to `/opt/munshi/bin/github-apply-staging-deploy-gateway`.
4. The forced-command gateway accepts only the Apply staging deployment command. It cannot invoke Hunter staging, Hunter production, Apply production, or arbitrary shell commands.
5. Netcup keeps Apply staging under `/home/munshi/munshi-apply-staging-v1`, separate from Hunter production and staging source trees. The deployment wrapper recreates only the Apply API service.
6. The wrapper verifies the Git bundle, requested SHA ancestry, clean worktree, safe Compose render, existing runtime/database health, exact OCI image revision, and unchanged Hunter staging/production container identities.
7. Existing Apply staging data is backed up before recreation. The prior image is retained as a rollback tag. Deployment writes a machine-readable receipt and rolls back automatically on failure.
8. Normal deployment refuses active prepare/submit proof workers. `MUNSHI_FINAL_REVIEW_ENABLED`, `MUNSHI_FINAL_SUBMIT_ENABLED`, and production submit authority remain false. The `hosted-submit-proof` profile is not activated by the deployment transport.
9. Bootstrap is a separate one-time root operation. It validates an exact clean approved source SHA, installs only Apply-specific wrappers, updates only the uniquely tagged Apply staging forced-key entry, validates `sshd`, and performs no deployment.

## Consequences

The Apply deployment key has a smaller blast radius than the existing Hunter deployment authority, and staging deployments are reproducible from GitHub without granting Netcup outbound GitHub source-fetch authority. The design adds a one-time operational bootstrap step and separate protected staging secrets before the first live deployment can run.

Controlled submit proof remains a later, explicit staging operation. This ADR authorizes staging source transport only; it does not authorize production deployment or enable final submission.

## Rejected alternatives

- Reuse the Hunter GitHub deployment key and gateway: rejected because it would unnecessarily expose Hunter production/staging deployment commands to Apply automation.
- Unrestricted SSH deployment key: rejected because arbitrary remote command execution is outside the required permission boundary.
- Server-side `git pull`/GitHub fetch: rejected because it weakens exact-source provenance and adds outbound source authority to the server.
- Automatic deployment on push: rejected because staging mutation must remain deliberate and exact-SHA based.
- Put Netcup bootstrap in `munshi-systems`: rejected for this tranche because the proven Netcup deployment foundation is associated with Hunter, while Systems currently serves a different product/deployment surface. Apply therefore owns its staging-specific transport contract and bootstrap source.
