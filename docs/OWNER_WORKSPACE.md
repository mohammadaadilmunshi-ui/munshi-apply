# Owner workspace source and release contract

The deployable owner workspace is tracked in `apps/owner-workspace`. It is a
standalone Sites application because its Cloudflare/Vinext build and lifecycle
are independent from the Edge extension workspaces in the root `package.json`.

## Source provenance

The initial recovered source snapshot in this monorepo matches owner-workspace
source commit `502f267cfeaf996adc0f17ad2ff7c284c9585c41`. Sites version 10 was built
from that exact source and its verified `dist` artifact.

## Release procedure

1. Make the same source change in `apps/owner-workspace` and the configured
   Sites source repository.
2. Run `npm ci`, `npm run lint`, and `npm test` inside
   `apps/owner-workspace`.
3. Push the exact source state before saving a Sites version. The Sites
   `commit_sha` must equal the pushed source commit.
4. Build the deployment archive from that exact commit and validate that it
   contains `dist/server/index.js` and `dist/.openai/hosting.json`.
5. Verify the current access policy before production deployment. Owner-only
   deployment must have exactly one owner, no groups, and no external visitors.
6. Deploy only a saved version, wait for a terminal deployment result, and keep
   final application submission manual.

The root CI workflow `.github/workflows/owner-workspace.yml` independently
installs, lints, builds, validates, and tests this application on pull requests.
