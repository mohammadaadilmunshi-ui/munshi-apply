# ADR-001: Monorepo with shared runtime contracts

- Status: Accepted
- Date: 2026-08-14

## Decision

Use an npm-workspace monorepo for the Edge extension and TypeScript domain packages, alongside a Python native companion. Zod schemas are the browser-side runtime contracts. Python models mirror event envelopes at the process boundary.

## Consequences

Contract changes are visible to all TypeScript consumers in one change. Cross-language compatibility requires explicit fixtures and versioned schemas rather than importing TypeScript types into Python.
