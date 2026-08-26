# ADR-002: Durable extension state

- Status: Accepted
- Date: 2026-08-14

## Decision

Treat the Manifest V3 service worker as an ephemeral coordinator. Store active-session UI state and page snapshots in IndexedDB as a recoverable browser cache. Do not depend on module variables for durable state. SQLite in the native companion is the authoritative long-term store for profiles, applications, events, evidence metadata, learning, and settings.

## Consequences

The side panel can recover after worker suspension, while loss or eviction of browser storage cannot erase the authoritative ledger. IndexedDB schema migrations and cache synchronization must preserve the SQLite authority boundary.
