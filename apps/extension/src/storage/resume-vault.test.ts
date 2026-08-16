import { describe, expect, it } from "vitest";
import type { ResumeRecord } from "./cloud";
import { resumeFamilyFor, resumeKindLabel } from "./resume-vault";

function resume(input: Partial<ResumeRecord> = {}): ResumeRecord {
  return {
    resumeId: "resume-test",
    objectId: "obj-test",
    name: "resume.pdf",
    contentType: "application/pdf",
    sizeBytes: 1024,
    addedAt: "2026-08-16T00:00:00.000Z",
    ...input,
  };
}

describe("resume vault classification helpers", () => {
  it("uses one durable master family", () => {
    expect(resumeFamilyFor("MASTER", null)).toBe("master");
    expect(resumeKindLabel(resume({ source: "MASTER" }))).toBe(
      "Master résumé",
    );
  });

  it("normalizes job and niche labels into tailored families", () => {
    expect(resumeFamilyFor("TAILORED", "People Analytics / HRIS")).toBe(
      "tailored:people-analytics-hris",
    );
    expect(
      resumeKindLabel(
        resume({ source: "TAILORED", roleFamily: "People Analytics" }),
      ),
    ).toBe("Tailored · People Analytics");
  });

  it("keeps imported files distinguishable until the owner classifies them", () => {
    expect(resumeFamilyFor("IMPORTED", null)).toBe("imported");
    expect(resumeKindLabel(resume({ source: "IMPORTED" }))).toBe(
      "Imported résumé",
    );
  });
});
