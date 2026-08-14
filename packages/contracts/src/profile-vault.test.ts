import { describe, expect, it } from "vitest";
import {
  ApplicationResumeSelectionSchema,
  ProfileRecordSchema,
  ProfileSnapshotSchema,
  ResumeVersionSchema,
} from "./profile-vault";

const now = "2026-08-14T18:00:00.000Z";

function employmentRecord(recordId: string, employer: string) {
  return ProfileRecordSchema.parse({
    recordId,
    kind: "EMPLOYMENT",
    label: employer,
    facts: [
      {
        factId: `${recordId}-employer`,
        key: "employer_name",
        value: employer,
        category: "EMPLOYMENT",
        trustLevel: "USER_CONFIRMED",
        source: "profile-record",
        confirmedAt: now,
        updatedAt: now,
        protected: false,
      },
    ],
    createdAt: now,
    updatedAt: now,
  });
}

describe("ProfileRecordSchema", () => {
  it("supports multiple structured employment records without flattening them", () => {
    const records = [
      employmentRecord("employment-1", "Employer One"),
      employmentRecord("employment-2", "Employer Two"),
    ];

    expect(records).toHaveLength(2);
    expect(records.map((record) => record.recordId)).toEqual([
      "employment-1",
      "employment-2",
    ]);
  });

  it("upgrades a legacy flat profile to a versioned empty record snapshot", () => {
    const snapshot = ProfileSnapshotSchema.parse({
      profileId: "profile-legacy",
      displayName: "Legacy profile",
      facts: [],
      createdAt: now,
      updatedAt: now,
      schemaVersion: 1,
    });

    expect(snapshot.snapshotVersion).toBe(1);
    expect(snapshot.records).toEqual([]);
    expect(snapshot.recordTombstones).toEqual([]);
  });

  it("rejects duplicate record ids and record/tombstone overlap", () => {
    const record = employmentRecord("employment-1", "Employer One");
    expect(() =>
      ProfileSnapshotSchema.parse({
        profileId: "profile-1",
        displayName: "Profile",
        facts: [],
        records: [record, record],
        recordTombstones: [],
        createdAt: now,
        updatedAt: now,
        schemaVersion: 1,
        snapshotVersion: 1,
      }),
    ).toThrow(/Duplicate profile record id/);

    expect(() =>
      ProfileSnapshotSchema.parse({
        profileId: "profile-1",
        displayName: "Profile",
        facts: [],
        records: [record],
        recordTombstones: [
          {
            recordId: record.recordId,
            kind: record.kind,
            deletedAt: now,
            confirmed: true,
          },
        ],
        createdAt: now,
        updatedAt: now,
        schemaVersion: 1,
        snapshotVersion: 1,
      }),
    ).toThrow(/Record and tombstone overlap/);
  });
});

describe("ResumeVersionSchema", () => {
  it("requires a content hash and positive immutable version number", () => {
    const resume = ResumeVersionSchema.parse({
      resumeId: "resume-1",
      family: "master",
      version: 1,
      sha256: "a".repeat(64),
      filename: "resume.pdf",
      contentType: "application/pdf",
      sizeBytes: 1024,
      source: "MASTER",
      roleFamily: null,
      active: true,
      createdAt: now,
    });

    expect(resume.sha256).toHaveLength(64);
    expect(resume.version).toBe(1);
  });

  it("rejects malformed resume hashes", () => {
    expect(() =>
      ResumeVersionSchema.parse({
        resumeId: "resume-1",
        family: "master",
        version: 1,
        sha256: "not-a-hash",
        filename: "resume.pdf",
        contentType: "application/pdf",
        sizeBytes: 1024,
        source: "MASTER",
        roleFamily: null,
        active: true,
        createdAt: now,
      }),
    ).toThrow();
  });
});

describe("ApplicationResumeSelectionSchema", () => {
  it("freezes the exact resume hash selected for an application", () => {
    const selection = ApplicationResumeSelectionSchema.parse({
      applicationId: "application-1",
      resumeId: "resume-1",
      resumeSha256: "b".repeat(64),
      lockedAt: now,
    });

    expect(selection.resumeSha256).toBe("b".repeat(64));
  });
});
