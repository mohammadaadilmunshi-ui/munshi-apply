import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import { describe, expect, it } from "vitest";
import { migrateLegacyProfileSnapshot } from "./profile-migration";

const now = "2026-08-14T12:00:00.000Z";

function legacyProfile(): ProfileSnapshot {
  return {
    profileId: "profile-1",
    displayName: "Profile",
    facts: [
      {
        factId: "fact-school",
        key: "school_name",
        value: "Montclair State University",
        category: "EDUCATION",
        trustLevel: "USER_CONFIRMED",
        source: "SIDE_PANEL",
        confirmedAt: now,
        updatedAt: now,
        protected: false,
      },
      {
        factId: "fact-employer",
        key: "current_employer",
        value: "Toyota Connected India",
        category: "EMPLOYMENT",
        trustLevel: "USER_CONFIRMED",
        source: "SIDE_PANEL",
        confirmedAt: now,
        updatedAt: now,
        protected: false,
      },
    ],
    records: [],
    recordTombstones: [],
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

describe("legacy profile migration", () => {
  it("seeds deterministic repeatable records without deleting flat facts", () => {
    const result = migrateLegacyProfileSnapshot(legacyProfile());

    expect(result.migrated).toBe(true);
    expect(result.snapshot.facts).toHaveLength(2);
    expect(result.snapshot.records.map((record) => record.kind)).toEqual([
      "EDUCATION",
      "EMPLOYMENT",
    ]);
    expect(result.snapshot.records[1]?.label).toBe("Toyota Connected India");
  });

  it("is idempotent after the first migration", () => {
    const first = migrateLegacyProfileSnapshot(legacyProfile());
    const second = migrateLegacyProfileSnapshot(first.snapshot);

    expect(second.migrated).toBe(false);
    expect(second.snapshot).toEqual(first.snapshot);
  });

  it("does not seed a legacy record over an existing record kind", () => {
    const first = migrateLegacyProfileSnapshot(legacyProfile()).snapshot;
    const second = migrateLegacyProfileSnapshot({
      ...first,
      facts: first.facts.map((fact) =>
        fact.key === "current_employer"
          ? { ...fact, value: "Changed legacy value" }
          : fact,
      ),
    });

    expect(second.migrated).toBe(false);
    expect(second.snapshot.records[1]?.label).toBe("Toyota Connected India");
  });
});
