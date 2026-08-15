import type { ProfileFact } from "@munshi-apply/contracts";
import type { ProfileSnapshot } from "@munshi-apply/contracts/profile-vault";
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
): ProfileSnapshot {
  return {
    profileId: "profile-test",
    displayName: "Test profile",
    facts,
    records: [],
    recordTombstones: [],
    createdAt: "2026-08-14T10:00:00.000Z",
    updatedAt,
    schemaVersion: 1,
    snapshotVersion: 1,
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

  it("preserves repeatable records when synchronizing with a legacy flat profile", () => {
    const local = {
      ...profile([], "2026-08-14T12:05:00.000Z"),
      records: [
        {
          recordId: "employment-1",
          kind: "EMPLOYMENT" as const,
          label: "Employer One",
          facts: [],
          sortOrder: 0,
          createdAt: "2026-08-14T12:00:00.000Z",
          updatedAt: "2026-08-14T12:05:00.000Z",
        },
      ],
    };
    const remote = profile([], "2026-08-14T12:06:00.000Z");

    expect(reconcileProtectedProfile(local, remote).records).toEqual(
      local.records,
    );
  });

  it("honors a newer explicitly confirmed record deletion", () => {
    const local = {
      ...profile([], "2026-08-14T12:06:00.000Z"),
      recordTombstones: [
        {
          recordId: "employment-1",
          kind: "EMPLOYMENT" as const,
          deletedAt: "2026-08-14T12:06:00.000Z",
          confirmed: true as const,
        },
      ],
    };
    const remote = {
      ...profile([], "2026-08-14T12:05:00.000Z"),
      records: [
        {
          recordId: "employment-1",
          kind: "EMPLOYMENT" as const,
          label: "Employer One",
          facts: [],
          sortOrder: 0,
          createdAt: "2026-08-14T12:00:00.000Z",
          updatedAt: "2026-08-14T12:05:00.000Z",
        },
      ],
    };

    const reconciled = reconcileProtectedProfile(local, remote);
    expect(reconciled.records).toEqual([]);
    expect(reconciled.recordTombstones).toEqual(local.recordTombstones);
  });

  it("blocks contradictory protected facts inside the same record", () => {
    const local = {
      ...profile([]),
      records: [
        {
          recordId: "education-1",
          kind: "EDUCATION" as const,
          label: "School",
          facts: [fact("graduation_date", "2026-12-16")],
          sortOrder: 0,
          createdAt: "2026-08-14T12:00:00.000Z",
          updatedAt: "2026-08-14T12:00:00.000Z",
        },
      ],
    };
    const remote = {
      ...profile([]),
      records: [
        {
          ...local.records[0]!,
          facts: [fact("graduation_date", "2027-01-01")],
        },
      ],
    };

    expect(protectedProfileConflictKeys(local, remote)).toEqual([
      "record:education-1:graduation_date",
    ]);
    expect(() => reconcileProtectedProfile(local, remote)).toThrow(
      /record:education-1:graduation_date/,
    );
  });
  it("preserves unrelated ordinary facts when a newer profile is sparse", () => {
    const local = profile(
      [
        fact("email", "aadil@example.test", { protected: false }),
        fact("preferred_name", "Aadil", { protected: false }),
      ],
      "2026-08-14T12:00:00.000Z",
    );
    const remote = profile(
      [
        fact("preferred_name", "Aadil M", {
          protected: false,
          updatedAt: "2026-08-14T12:05:00.000Z",
        }),
      ],
      "2026-08-14T12:05:00.000Z",
    );

    const reconciled = reconcileProtectedProfile(local, remote);
    expect(
      reconciled.facts.find((candidate) => candidate.key === "email")?.value,
    ).toBe("aadil@example.test");
    expect(
      reconciled.facts.find((candidate) => candidate.key === "preferred_name")
        ?.value,
    ).toBe("Aadil M");
  });

  it("resolves confirmed protected conflicts only after an explicit owner winner", () => {
    const local = profile(
      [fact("first_name", "Mohammad Aadil Vasim")],
      "2026-08-14T12:02:00.000Z",
    );
    const remote = profile(
      [fact("first_name", "Mohammad Aadil")],
      "2026-08-14T12:03:00.000Z",
    );

    expect(() => reconcileProtectedProfile(local, remote)).toThrow(
      /first_name/,
    );
    expect(
      reconcileProtectedProfile(local, remote, "local").facts.find(
        (candidate) => candidate.key === "first_name",
      )?.value,
    ).toBe("Mohammad Aadil Vasim");
    expect(
      reconcileProtectedProfile(local, remote, "remote").facts.find(
        (candidate) => candidate.key === "first_name",
      )?.value,
    ).toBe("Mohammad Aadil");
  });
});
