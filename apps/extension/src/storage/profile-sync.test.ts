import type { MasterProfile, ProfileFact } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import {
  protectedProfileConflictKeys,
  reconcileProtectedProfile,
} from "./profile-sync";

function fact(
  key: string,
  value: ProfileFact["value"],
  options: {
    protected?: boolean;
    trustLevel?: ProfileFact["trustLevel"];
    updatedAt?: string;
  } = {},
): ProfileFact {
  return {
    factId: `fact-${key}-${String(value)}`,
    key,
    value,
    category: "IDENTITY",
    trustLevel: options.trustLevel ?? "USER_CONFIRMED",
    source: "TEST",
    confirmedAt:
      (options.trustLevel ?? "USER_CONFIRMED") === "UNKNOWN"
        ? null
        : "2026-08-14T12:00:00.000Z",
    updatedAt: options.updatedAt ?? "2026-08-14T12:00:00.000Z",
    protected: options.protected ?? true,
  };
}

function profile(
  facts: ProfileFact[],
  updatedAt = "2026-08-14T12:00:00.000Z",
): MasterProfile {
  return {
    profileId: "profile-test",
    displayName: "Test profile",
    facts,
    createdAt: "2026-08-14T10:00:00.000Z",
    updatedAt,
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

  it("accepts the same protected value without changing the newer base", () => {
    const local = profile(
      [fact("future_sponsorship", "Yes")],
      "2026-08-14T12:00:00.000Z",
    );
    const remote = profile(
      [fact("future_sponsorship", "Yes")],
      "2026-08-14T12:01:00.000Z",
    );

    expect(protectedProfileConflictKeys(local, remote)).toEqual([]);
    expect(reconcileProtectedProfile(local, remote)).toEqual(remote);
  });

  it("preserves a remote confirmed value over a newer local draft", () => {
    const local = profile(
      [fact("legal_name", "Local draft", { trustLevel: "UNKNOWN" })],
      "2026-08-14T12:02:00.000Z",
    );
    const remote = profile(
      [fact("legal_name", "Confirmed name")],
      "2026-08-14T12:01:00.000Z",
    );

    const reconciled = reconcileProtectedProfile(local, remote);
    expect(
      reconciled.facts.find((candidate) => candidate.key === "legal_name")
        ?.value,
    ).toBe("Confirmed name");
  });

  it("preserves a local confirmed value when the newer remote profile lacks it", () => {
    const local = profile(
      [fact("work_authorization", "Authorized")],
      "2026-08-14T12:00:00.000Z",
    );
    const remote = profile(
      [fact("preferred_name", "Aadil", { protected: false })],
      "2026-08-14T12:05:00.000Z",
    );

    const reconciled = reconcileProtectedProfile(local, remote);
    expect(
      reconciled.facts.find(
        (candidate) => candidate.key === "work_authorization",
      )?.value,
    ).toBe("Authorized");
    expect(
      reconciled.facts.find((candidate) => candidate.key === "preferred_name")
        ?.value,
    ).toBe("Aadil");
  });

  it("lets the newer base win ordinary non-protected edits", () => {
    const local = profile(
      [fact("preferred_name", "Old", { protected: false })],
      "2026-08-14T12:00:00.000Z",
    );
    const remote = profile(
      [fact("preferred_name", "New", { protected: false })],
      "2026-08-14T12:05:00.000Z",
    );

    expect(
      reconcileProtectedProfile(local, remote).facts.find(
        (candidate) => candidate.key === "preferred_name",
      )?.value,
    ).toBe("New");
  });
});
