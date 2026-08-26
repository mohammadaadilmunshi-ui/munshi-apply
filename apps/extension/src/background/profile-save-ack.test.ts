import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { describe, expect, it } from "vitest";

function stableContent(snapshot: ProfileSnapshot): string {
  return JSON.stringify({ ...snapshot, updatedAt: "SYNC_ACK" });
}

function fixture(updatedAt: string): ProfileSnapshot {
  return {
    profileId: "profile-test",
    displayName: "My application profile",
    facts: [
      {
        factId: "fact-first-name",
        key: "first_name",
        value: "Aadil",
        category: "IDENTITY",
        trustLevel: "USER_CONFIRMED",
        source: "SIDE_PANEL",
        confirmedAt: "2026-08-15T01:00:00.000Z",
        updatedAt: "2026-08-15T01:00:00.000Z",
        protected: true,
      },
    ],
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-15T00:00:00.000Z",
    updatedAt,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

describe("profile save acknowledgement content", () => {
  it("treats a sync-only top-level updatedAt advance as the same saved content", () => {
    const before = fixture("2026-08-15T01:00:00.000Z");
    const synchronized = fixture("2026-08-15T01:00:02.000Z");
    expect(stableContent(synchronized)).toBe(stableContent(before));
  });

  it("still detects a real fact change", () => {
    const before = fixture("2026-08-15T01:00:00.000Z");
    const changed = fixture("2026-08-15T01:00:02.000Z");
    changed.facts = changed.facts.map((fact) => ({
      ...fact,
      value: "Different",
    }));
    expect(stableContent(changed)).not.toBe(stableContent(before));
  });
});
