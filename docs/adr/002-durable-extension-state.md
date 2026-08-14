# ADR-002: Durable extension state

- Status: Accepted
- Date: 2026-08-14

## Decision

Treat the Manifest V3 service worker as an ephemeral coordinator. Store the Master Profile and page snapshots in IndexedDB. Do not depend on module variables for authoritative state.

## Consequences

The side panel can recover after worker suspension. IndexedDB schema migrations and cache/authority boundaries must be managed as the application grows.
