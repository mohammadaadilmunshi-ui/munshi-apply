import { describe, expect, it } from "vitest";
import { retrieveEvidenceHybrid } from "./retrieval";
import { planJobResponse } from "./job-response";
import type { EvidenceGraph } from "./evidence";

describe("hybrid evidence retrieval", () => {
  it("brings job context and candidate evidence into a why-role context without protected/generated evidence", () => {
    const graph: EvidenceGraph = {
      nodes: [
        {
          evidenceId: "job",
          kind: "JOB_REQUIREMENT",
          text: "Coordinate consultant recruiting and candidate operations",
          semanticTypes: ["WHY_ROLE"],
          trustLevel: "DOCUMENT_CONFIRMED",
          protected: false,
          source: "job-listing",
          updatedAt: "2026-08-17T00:00:00Z",
        },
        {
          evidenceId: "resume",
          kind: "RESUME_BULLET",
          text: "Recruiting operations experience with onboarding and candidate coordination",
          semanticTypes: ["RELEVANT_EXPERIENCE"],
          trustLevel: "DOCUMENT_CONFIRMED",
          protected: false,
          source: "resume:r1",
          updatedAt: "2026-08-17T00:00:00Z",
        },
        {
          evidenceId: "secret",
          kind: "PROFILE_FACT",
          text: "protected fact",
          semanticTypes: ["WHY_ROLE"],
          trustLevel: "VERIFIED",
          protected: true,
          source: "profile",
          updatedAt: "2026-08-17T00:00:00Z",
        },
      ],
      edges: [],
    };
    const hits = retrieveEvidenceHybrid(graph, {
      query: "Why this recruiting role?",
      semanticType: "WHY_ROLE",
      plan: planJobResponse("Why this role?", "WHY_ROLE"),
    });
    expect(hits.map((item) => item.node.evidenceId)).toContain("job");
    expect(hits.map((item) => item.node.evidenceId)).toContain("resume");
    expect(hits.map((item) => item.node.evidenceId)).not.toContain("secret");
  });
});
