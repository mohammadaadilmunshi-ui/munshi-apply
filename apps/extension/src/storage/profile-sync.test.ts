import type { MasterProfile, ProfileFact } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import { protectedProfileConflictKeys } from "./profile-sync";

function fact(
  key: string,
  value: ProfileFact["value"],
  options: { protected?: boolean; trustLevel?: ProfileFact["trustLevel"] } = {},
): ProfileFact {
  return {
    factId: `fact-${key}`,
    key,
    value,
    category: "IDENTITY",
    trustLevel: options.trustLevel ?? "USER_CONFIRMED",
    source: "TEST",
    confirmedAt: "2026-08-14T12:00:00.000Z",
    updatedAt: "2026-08-14T12:00:00.000Z",
    protected: options.protected ?? true,
  };
}

function profile(facts: ProfileFact[]): MasterProfile {
  return {
    profileId: "profile-test",
    displayName: "Test profile",
    facts,
    createdAt: "2026-08-14T12:00:00.000Z",
    updatedAt: "2026-08-14T12:00:00.000Z",
    schemaVersion: 1,
  };
}

describe("protected profile convergence", () => {
  it("detects different confirmed protected values", () => {
    const local = profile([fact("work_authorization", "Authorized")]);
    const remote = profile([fact("work_authorization", "Not authorized")]);

    expect(protectedProfileConflictKeys(local, remote)).toEqual([
      "work_authorization",
    ]);
  });

  it("accepts the same protected value", () => {
    const local = profile([fact("future_sponsorship", "Yes")]);
    const remote = profile([fact("future_sponsorship", "Yes")]);

    expect(protectedProfileConflictKeys(local, remote)).toEqual([]);
  });

  it("does not treat an unconfirmed protected draft as a conflict", () => {
    const local = profile([
      fact("legal_name", "Local draft", { trustLevel: "UNKNOWN" }),
    ]);
    const remote = profile([fact("legal_name", "Confirmed name")]);

    expect(protectedProfileConflictKeys(local, remote)).toEqual([]);
  });

  it("does not block ordinary non-protected edits", () => {
    const local = profile([fact("preferred_name", "A", { protected: false })]);
    const remote = profile([fact("preferred_name", "B", { protected: false })]);

    expect(protectedProfileConflictKeys(local, remote)).toEqual([]);
  });
});
