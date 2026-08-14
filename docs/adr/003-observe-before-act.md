# ADR-003: Observe before act

- Status: Accepted
- Date: 2026-08-14

## Decision

Ship universal discovery, semantic understanding, profile protection, and diagnostics before enabling writes to employer pages. Autofill requires separate pre-flight, verification, checkpointing, and recovery milestones.

## Consequences

The first milestone is useful for page mapping and architecture validation but cannot complete applications. This prevents early interaction code from outrunning safety and evidence controls.
