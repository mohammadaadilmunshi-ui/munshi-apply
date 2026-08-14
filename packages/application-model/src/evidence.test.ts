import { describe, expect, it } from "vitest";
import {
  evidenceHasContradiction,
  retrieveEvidence,
  type EvidenceGraph,
} from "./evidence";

const graph: EvidenceGraph = {
  nodes: [
    {
      evidenceId: "employment-verified",
      kind: "EMPLOYMENT",
      text: "Recruiting operations, candidate interviews, and onboarding documentation",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "VERIFIED",
      protected: false,
      source: "verified-employment-record",
      updatedAt: "2026-08-14T12:00:00.000Z",
    },
    {
      evidenceId: "employment-generated",
      kind: "EMPLOYMENT",
      text: "Recruiting operations and candidate interviews",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "GENERATED",
      protected: false,
      source: "generated-draft",
      updatedAt: "2026-08-14T13:00:00.000Z",
    },
    {
      evidenceId: "protected-authorization",
      kind: "PROFILE_FACT",
      text: "Confirmed work authorization answer",
      semanticTypes: ["WORK_AUTHORIZATION_CURRENT"],
      trustLevel: "USER_CONFIRMED",
      protected: true,
      source: "protected-profile-fact",
      updatedAt: "2026-08-14T14:00:00.000Z",
    },
    {
      evidenceId: "education",
      kind: "EDUCATION",
      text: "Human Resource and Analytics graduate program",
      semanticTypes: ["EDUCATION"],
      trustLevel: "DOCUMENT_CONFIRMED",
      protected: false,
      source: "education-document",
      updatedAt: "2026-08-13T12:00:00.000Z",
    },
  ],
  edges: [
    {
      fromEvidenceId: "employment-verified",
      toEvidenceId: "education",
      relation: "CONTRADICTS",
    },
  ],
};

describe("retrieveEvidence", () => {
  it("prefers semantically matching verified evidence", () => {
    const result = retrieveEvidence(graph, {
      query: "Describe recruiting experience",
      semanticType: "RELEVANT_EXPERIENCE",
    });

    expect(result.items.map((item) => item.evidenceId)).toEqual([
      "employment-verified",
    ]);
    expect(result.items[0]?.semanticMatch).toBe(true);
  });

  it("does not treat generated text as verified evidence by default", () => {
    const result = retrieveEvidence(graph, {
      query: "recruiting candidate interviews",
      semanticType: "RELEVANT_EXPERIENCE",
    });

    expect(result.items.some((item) => item.evidenceId === "employment-generated")).toBe(
      false,
    );
    expect(result.excludedByTrustCount).toBe(1);
  });

  it("excludes protected evidence unless the caller explicitly allows it", () => {
    const blocked = retrieveEvidence(graph, {
      query: "work authorization",
      semanticType: "WORK_AUTHORIZATION_CURRENT",
    });
    expect(blocked.items).toEqual([]);
    expect(blocked.blockedProtectedCount).toBe(1);

    const allowed = retrieveEvidence(graph, {
      query: "work authorization",
      semanticType: "WORK_AUTHORIZATION_CURRENT",
      includeProtected: true,
    });
    expect(allowed.items.map((item) => item.evidenceId)).toEqual([
      "protected-authorization",
    ]);
  });

  it("validates bounded result sizes", () => {
    expect(() =>
      retrieveEvidence(graph, {
        query: "experience",
        semanticType: "RELEVANT_EXPERIENCE",
        maxResults: 0,
      }),
    ).toThrow("maxResults must be an integer between 1 and 25");
  });
});

describe("evidenceHasContradiction", () => {
  it("reports contradictions only when both linked evidence items are selected", () => {
    expect(
      evidenceHasContradiction(graph, ["employment-verified", "education"]),
    ).toBe(true);
    expect(evidenceHasContradiction(graph, ["employment-verified"])).toBe(false);
  });
});
