# Hosted owner workspace UI and source-control contract

Status: required M1/M0.5 release contract.

## Purpose

The responsive owner workspace is a separate runtime from the Edge extension and macOS native companion. Its production UI must nevertheless use the same canonical cross-device state and safety rules as the desktop workflow.

The currently deployed `chatgpt.site` workspace predates source-controlled ownership of its frontend. Until its exact deployment source is imported into this repository and the tracked implementation is redeployed, the hosted UI is not considered reproducible from GitHub and M1 hosted-workspace parity remains incomplete.

No replacement host, paid service, domain change, re-pairing, or credential migration may be performed merely to close this gap. Deployment requires the existing hosted runtime/source or a separately authorized migration plan.

## Canonical source location

The eventual hosted frontend source must live under:

```text
apps/owner-workspace/
```

or another repository location approved by an ADR before deployment. It may not remain as an untracked production-only artifact.

Shared cross-runtime presentation/state rules belong in `@munshi-apply/shared`. The owner workspace and extension must consume the same rules rather than independently interpreting counters or sync state.

## Overview authority

One authoritative workspace snapshot supplies these counters:

```text
activeDeviceCount
confirmedFactCount
encryptedResumeCount
answersToReviewCount
syncEventCount
historicalConflictCount
unresolvedConflictCount
```

A page may not combine one counter from a public/control endpoint with another counter from an unrelated local cache and present them as one coherent status card.

### Count rendering

Every count has one of three explicit states:

```text
loading -> Loading…
ready  -> exact integer, including 0
error  -> Unable to load
```

A dash (`—`) is prohibited as a device-count or workspace-count fallback because it conflates loading, zero, unsupported, and failed states.

Therefore, when the authority reports one active device, every owner-workspace surface that labels the same concept must show:

```text
1 active device
```

not:

```text
— paired devices
```

Terminology should prefer `active devices` for the cloud inventory. `Paired` describes the enrollment relationship; `active` is the count exposed by the current device inventory.

## Conflict presentation

Historical synchronization conflicts and currently unresolved conflicts are different concepts and must never share one ambiguous counter.

Primary owner-facing status:

```text
Unresolved conflicts: N
```

Historical/audit context:

```text
N historical conflict events
```

Only unresolved conflicts are an active attention state. A historical conflict event remains useful for auditing but must not visually imply that the workspace is currently unsafe or blocked.

The UI must not assume that a historical conflict is resolved. The server/control-plane snapshot must provide both counts explicitly.

## Autosync-first interaction

Normal workspace edits use automatic save/synchronization.

Expected status progression:

```text
Editing…
Saving…
Encrypted & synced
```

`Encrypted & synced` may appear only after the cloud has acknowledged the exact current entity version. A queued write or a successful request for an older revision is not sufficient.

Protected facts remain different:

```text
edit draft
-> deliberate confirmation
-> encrypted write
-> exact-version acknowledgement
-> synced
```

A partial protected value must never become canonical merely because a debounce timer fired.

### Manual sync action

A top-level `Sync` button must not be the normal persistence mechanism.

Allowed fallback states:

```text
idle/manual diagnostic -> Sync now
sync error             -> Retry sync
retry in progress      -> disabled Retry sync
saving/synced          -> no prominent manual sync button
```

The owner should not need to remember to press Sync after ordinary edits or résumé operations.

## Profile parity

The hosted Profile must use the same canonical profile fact keys and protection semantics as the desktop extension. Hosted parity includes the complete structured profile model, not only the original starter fields.

Protected facts must use deliberate confirmation and the same cross-device conflict policy as the desktop extension. The hosted frontend may improve layout for mobile, but it may not redefine the meaning, protection level, or authority of a fact.

## Resume and review parity

Résumé uploads are encrypted before durable cloud storage and synchronize immediately after successful encryption/upload. Application review decisions and selected résumé IDs are versioned application state, not transient UI state.

The final submit boundary remains manual on every surface.

## Device inventory

The Devices surface is the canonical owner inventory. It must expose, when available from the control plane:

```text
device identity/label
platform
last use
capabilities
active/revoked state
revoke action
```

The Overview active-device count must be derived from the same inventory authority.

## Release gates for the hosted UI

A hosted UI release is not verified until all of the following pass with synthetic data:

1. outer/control and inner/private workspace show the same active-device count;
2. zero is rendered as `0`, loading as `Loading…`, and failures as `Unable to load`;
3. historical and unresolved conflicts are displayed separately;
4. ordinary edits autosave without a required Sync click;
5. protected facts require deliberate confirmation;
6. current-version acknowledgement is required before `Encrypted & synced`;
7. résumé upload/list/review survives refresh and cross-device synchronization;
8. device inventory and Overview count converge after enrollment or revocation;
9. recovery restore reproduces the synthetic profile and résumé in a fresh client;
10. the deployed hosted source corresponds to a committed, reproducible repository revision.

## Current deployment boundary

The existing owner workspace remains operational and must not be broken merely to satisfy source-control cleanup. The current GitHub/Vercel connections do not expose that `chatgpt.site` frontend as an editable deployment target. Therefore this repository can enforce the shared contract and regression tests now, but the visible hosted pixels change only when the tracked source is attached to the existing runtime or an owner-authorized deployment migration is performed.
