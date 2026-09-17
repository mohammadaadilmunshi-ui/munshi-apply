import { describe, expect, it } from "vitest";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
import {
  permanentProfileTarget,
  promoteRememberedAnswerIntoProfile,
} from "./profile-answer-promotion";

function profile(): ProfileSnapshot {
  return {
    profileId: "profile-remember",
    displayName: "My application profile",
    facts: [],
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-25T07:00:00.000Z",
    updatedAt: "2026-08-25T07:00:00.000Z",
    schemaVersion: 1,
    snapshotVersion: 1,
  };
}

describe("remembered answer profile promotion", () => {
  it("promotes an approved permanent answer into the canonical visible profile fact", () => {
    const result = promoteRememberedAnswerIntoProfile(profile(), {
      semanticType: "SPONSORSHIP_FUTURE",
      value: "Yes",
      sensitive: true,
      approvedAt: "2026-08-25T07:30:00.000Z",
    });

    expect(result.changed).toBe(true);
    expect(result.key).toBe("future_sponsorship");
    expect(result.profile.facts).toEqual([
      expect.objectContaining({
        key: "future_sponsorship",
        value: "Yes",
        category: "SPONSORSHIP",
        trustLevel: "USER_CONFIRMED",
        source: "REMEMBERED_APPLICATION_ANSWER",
        confirmedAt: "2026-08-25T07:30:00.000Z",
        protected: true,
      }),
    ]);
  });

  it("keeps permanent profile targets aligned with existing profile fields", () => {
    expect(permanentProfileTarget("EMAIL")).toEqual({
      key: "email",
      category: "CONTACT",
      protected: false,
    });
    expect(permanentProfileTarget("RELOCATION")).toEqual({
      key: "relocation_willingness",
      category: "WORK_PREFERENCE",
      protected: false,
    });
  });

  it("does not globalize employer-specific, narrative, or semantically overloaded answers", () => {
    expect(permanentProfileTarget("PREVIOUS_APPLICATION")).toBeNull();
    expect(permanentProfileTarget("WHY_COMPANY")).toBeNull();
    expect(permanentProfileTarget("WORK_AUTHORIZATION_CURRENT")).toBeNull();
    expect(permanentProfileTarget("SALARY_EXPECTATION")).toBeNull();
    expect(permanentProfileTarget("START_DATE")).toBeNull();
    expect(permanentProfileTarget("RACE_ETHNICITY")).toBeNull();
  });

  it("does not rewrite an already authoritative matching profile fact", () => {
    const existing = profile();
    existing.facts.push({
      factId: "fact-email",
      key: "email",
      value: "candidate@example.com",
      category: "CONTACT",
      trustLevel: "USER_CONFIRMED",
      source: "SIDE_PANEL",
      confirmedAt: "2026-08-25T07:10:00.000Z",
      updatedAt: "2026-08-25T07:10:00.000Z",
      protected: false,
    });

    const result = promoteRememberedAnswerIntoProfile(existing, {
      semanticType: "EMAIL",
      value: "candidate@example.com",
      sensitive: false,
      approvedAt: "2026-08-25T07:30:00.000Z",
    });

    expect(result.changed).toBe(false);
    expect(result.profile).toBe(existing);
  });
});
