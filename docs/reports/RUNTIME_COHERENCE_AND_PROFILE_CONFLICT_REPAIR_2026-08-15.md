# Runtime Coherence and Protected Profile Conflict Repair — 2026-08-15

## Diagnosis

The Edge extension and installed macOS native companion could drift because the normal local update loop rebuilt only JavaScript artifacts. A legacy native companion could still answer `PING`, causing the extension to report a healthy connection while newer AI messages failed with `Unsupported native message`.

The protected-profile synchronizer correctly detected conflicting confirmed protected values, but the desktop side panel had no explicit owner resolution path and treated the conflict too much like a transport error. The AI permission checkboxes also inherited full-width text-input CSS.

## Repair

- Native `PING` now advertises protocol version 2 and explicit capabilities.
- The extension fails closed on native protocol mismatch and labels it `Companion update` instead of calling unsupported native features.
- `scripts/update-local-runtime.sh` updates both the extension and the installed native Python package, preserves the existing runtime/database, applies migrations, and runs the native smoke test.
- Confirmed protected profile conflicts remain fail-closed until the owner explicitly chooses either the Mac values or encrypted-workspace values.
- Conflict saves remain locally durable but no longer enter an automatic retry storm or falsely report synchronized.
- The Profile UI shows both conflicting values and explicit resolution actions.
- AI checkbox/radio controls no longer inherit text-field width/padding.
- AI status distinguishes API-key configuration from MUNSHI/native connectivity, and native errors are rendered as errors rather than success notices.

## Invariants preserved

- No protected value is silently selected.
- No encrypted history is deleted.
- No pairing, credential, Keychain item, or database is reset by the code repair.
- Final submission and security checkpoints remain manual.
- PR #11 remains draft and unmerged unless separately authorized.
