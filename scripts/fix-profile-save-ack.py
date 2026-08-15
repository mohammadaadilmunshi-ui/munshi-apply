from pathlib import Path

service = Path("apps/extension/src/background/service-worker.ts")
text = service.read_text()
old_import = 'import { parseProfileSnapshot } from "@munshi-apply/contracts/profile-vault";'
new_import = '''import {
  parseProfileSnapshot,
  type ProfileSnapshot,
} from "@munshi-apply/contracts/profile-vault";'''
if old_import not in text:
    raise SystemExit("profile-vault import anchor missing")
text = text.replace(old_import, new_import, 1)

anchor = 'let initialized = false;\n'
helper = '''let initialized = false;\n\nfunction sameProfileSaveContent(\n  left: ProfileSnapshot,\n  right: ProfileSnapshot,\n): boolean {\n  return (\n    JSON.stringify({ ...left, updatedAt: "SYNC_ACK" }) ===\n    JSON.stringify({ ...right, updatedAt: "SYNC_ACK" })\n  );\n}\n'''
if anchor not in text:
    raise SystemExit("initialized anchor missing")
text = text.replace(anchor, helper, 1)

old_block = '''          if (JSON.stringify(synchronized) !== JSON.stringify(parsed)) {\n            throw new Error(\n              "Profile changed on another device. Refresh before saving again.",\n            );\n          }'''
new_block = '''          if (!sameProfileSaveContent(synchronized, parsed)) {\n            throw new Error(\n              "Profile content changed on another device. Refresh before saving again.",\n            );\n          }'''
if old_block not in text:
    raise SystemExit("save acknowledgement block missing")
text = text.replace(old_block, new_block, 1)
service.write_text(text)

# Add focused regression coverage for the acknowledgement semantics.
test = Path("apps/extension/src/background/profile-save-ack.test.ts")
test.write_text('''import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";\nimport { describe, expect, it } from "vitest";\n\nfunction stableContent(snapshot: ProfileSnapshot): string {\n  return JSON.stringify({ ...snapshot, updatedAt: "SYNC_ACK" });\n}\n\nfunction fixture(updatedAt: string): ProfileSnapshot {\n  return {\n    profileId: "profile-test",\n    displayName: "My application profile",\n    facts: [\n      {\n        factId: "fact-first-name",\n        key: "first_name",\n        value: "Aadil",\n        category: "IDENTITY",\n        trustLevel: "USER_CONFIRMED",\n        source: "SIDE_PANEL",\n        confirmedAt: "2026-08-15T01:00:00.000Z",\n        updatedAt: "2026-08-15T01:00:00.000Z",\n        protected: true,\n      },\n    ],\n    records: [],\n    recordTombstones: [],\n    createdAt: "2026-08-15T00:00:00.000Z",\n    updatedAt,\n    schemaVersion: 1,\n    snapshotVersion: 1,\n  };\n}\n\ndescribe("profile save acknowledgement content", () => {\n  it("treats a sync-only top-level updatedAt advance as the same saved content", () => {\n    const before = fixture("2026-08-15T01:00:00.000Z");\n    const synchronized = fixture("2026-08-15T01:00:02.000Z");\n    expect(stableContent(synchronized)).toBe(stableContent(before));\n  });\n\n  it("still detects a real fact change", () => {\n    const before = fixture("2026-08-15T01:00:00.000Z");\n    const changed = fixture("2026-08-15T01:00:02.000Z");\n    changed.facts = changed.facts.map((fact) => ({ ...fact, value: "Different" }));\n    expect(stableContent(changed)).not.toBe(stableContent(before));\n  });\n});\n''')
