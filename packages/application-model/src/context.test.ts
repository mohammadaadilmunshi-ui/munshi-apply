import { describe, expect, it } from "vitest";
import { assembleEvidenceContext, validateGeneratedDraft } from "./context";
import type { EvidenceContext, EvidenceGraph } from "./evidence";

const evidence: EvidenceContext = {
  query: "Describe recruiting experience",
  semanticType: "RELEVANT_EXPERIENCE",
  items: [
    {
      evidenceId: "e-1",
      kind: "EMPLOYMENT",
      text: "Verified recruiting and onboarding experience",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "VERIFIED",
      protected: false,
      source: "employment-record",
      updatedAt: "2026-08-14T18:00:00.000Z",
      score: 0.95,
      semanticMatch: true,
      tokenOverlap: 0.5,
    },
    {
      evidenceId: "e-2",
      kind: "RESUME_BULLET",
      text: "Verified candidate interview evidence",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "DOCUMENT_CONFIRMED",
      protected: false,
      source: "resume",
      updatedAt: "2026-08-14T17:00:00.000Z",
      score: 0.9,
      semanticMatch: true,
      tokenOverlap: 0.3,
    },
  ],
  blockedProtectedCount: 1,
  excludedByTrustCount: 1,
};

const graph: EvidenceGraph = {
  nodes: evidence.items,
  edges: [
    {
      fromEvidenceId: "e-1",
      toEvidenceId: "e-2",
      relation: "CONTRADICTS",
    },
  ],
};

describe("assembleEvidenceContext", () => {
  it("bounds context by item count and characters", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 1,
      maxCharacters: 1000,
    });

    expect(context.items.map((item) => item.evidenceId)).toEqual(["e-1"]);
    expect(context.truncated).toBe(true);
    expect(context.excludedEvidenceCount).toBe(1);
  });

  it("never partially slices an evidence item to fit a character budget", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 5,
      maxCharacters: 10,
    });

    expect(context.items).toEqual([]);
    expect(context.characterCount).toBe(0);
    expect(context.truncated).toBe(true);
  });
});

describe("validateGeneratedDraft", () => {
  it("requires every structured claim to cite available evidence", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 2,
      maxCharacters: 1000,
    });
    const result = validateGeneratedDraft(
      {
        text: "I have recruiting experience.",
        claims: [
          {
            claimId: "claim-1",
            text: "I have recruiting experience",
            evidenceIds: ["missing-evidence"],
          },
        ],
      },
      context,
      graph,
    );

    expect(result.valid).toBe(false);
    expect(result.unsupportedClaimIds).toEqual(["claim-1"]);
  });

  it("detects contradictory evidence selected for one claim", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 2,
      maxCharacters: 1000,
    });
    const result = validateGeneratedDraft(
      {
        text: "Claim backed by conflicting sources.",
        claims: [
          {
            claimId: "claim-1",
            text: "Conflicting claim",
            evidenceIds: ["e-1", "e-2"],
          },
        ],
      },
      context,
      graph,
    );

    expect(result.valid).toBe(false);
    expect(result.contradictoryClaimIds).toEqual(["claim-1"]);
  });

  it("rejects unstructured non-empty generated prose", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 2,
      maxCharacters: 1000,
    });
    const result = validateGeneratedDraft(
      { text: "Unsupported prose", claims: [] },
      context,
      graph,
    );

    expect(result.missingClaimStructure).toBe(true);
    expect(result.valid).toBe(false);
  });

  it("enforces a requested word limit", () => {
    const context = assembleEvidenceContext(evidence, {
      maxItems: 2,
      maxCharacters: 1000,
    });
    const result = validateGeneratedDraft(
      {
        text: "one two three four",
        claims: [{ claimId: "claim-1", text: "claim", evidenceIds: ["e-1"] }],
      },
      context,
      { ...graph, edges: [] },
      { maxWords: 3 },
    );

    expect(result.exceedsWordLimit).toBe(true);
    expect(result.wordCount).toBe(4);
    expect(result.valid).toBe(false);
  });
});
