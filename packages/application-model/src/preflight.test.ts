import type {
  ApplicationPage,
  MasterProfile,
  ProfileFact,
  Question,
} from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import type { EvidenceGraph } from "./evidence";
import { buildPreflightAssessment } from "./preflight";

const now = "2026-08-14T18:30:00.000Z";

function fact(overrides: Partial<ProfileFact>): ProfileFact {
  return {
    factId: "fact-1",
    key: "first_name",
    value: "Aadil",
    category: "IDENTITY",
    trustLevel: "USER_CONFIRMED",
    source: "profile",
    confirmedAt: now,
    updatedAt: now,
    protected: false,
    ...overrides,
  };
}

function profile(facts: ProfileFact[]): MasterProfile {
  return {
    profileId: "profile-1",
    displayName: "Test profile",
    facts,
    createdAt: now,
    updatedAt: now,
    schemaVersion: 1,
  };
}

function question(overrides: Partial<Question>): Question {
  return {
    questionId: "question-1",
    controlId: "control-1",
    rawText: "First name",
    semanticType: "FIRST_NAME",
    confidence: 0.95,
    sensitive: false,
    requiresReview: false,
    ...overrides,
  };
}

function page(
  questions: Question[],
  requiredControlIds: readonly string[] = [],
): ApplicationPage {
  return {
    pageId: "page-1",
    tabId: 1,
    frameId: 0,
    documentId: "document-1",
    url: "https://example.com/apply",
    title: "Application",
    observedAt: now,
    controls: questions.map((item) => ({
      controlId: item.controlId,
      frameId: 0,
      kind: "TEXT",
      tagName: "input",
      name: item.controlId,
      label: item.rawText,
      placeholder: "",
      ariaLabel: "",
      required: requiredControlIds.includes(item.controlId),
      disabled: false,
      visible: true,
      options: [],
    })),
    questions,
  };
}

const contradictionGraph: EvidenceGraph = {
  nodes: [
    {
      evidenceId: "evidence-a",
      kind: "EMPLOYMENT",
      text: "Evidence A",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "VERIFIED",
      protected: false,
      source: "record-a",
      updatedAt: now,
    },
    {
      evidenceId: "evidence-b",
      kind: "EMPLOYMENT",
      text: "Evidence B",
      semanticTypes: ["RELEVANT_EXPERIENCE"],
      trustLevel: "VERIFIED",
      protected: false,
      source: "record-b",
      updatedAt: now,
    },
  ],
  edges: [
    {
      fromEvidenceId: "evidence-a",
      toEvidenceId: "evidence-b",
      relation: "CONTRADICTS",
    },
  ],
};

describe("buildPreflightAssessment", () => {
  it("is ready when every question has an authoritative ordinary answer", () => {
    const result = buildPreflightAssessment({
      page: page([question({})]),
      profile: profile([fact({})]),
    });

    expect(result.state).toBe("READY");
    expect(result.requiredUnresolvedCount).toBe(0);
    expect(result.blockingReasons).toEqual([]);
  });

  it("blocks a required unresolved question", () => {
    const unresolved = question({
      rawText: "Why this company?",
      semanticType: "WHY_COMPANY",
    });
    const result = buildPreflightAssessment({
      page: page([unresolved], [unresolved.controlId]),
      profile: profile([]),
    });

    expect(result.state).toBe("BLOCKED");
    expect(result.requiredUnresolvedCount).toBe(1);
    expect(result.blockingReasons[0]).toContain("required question");
  });

  it("forces protected knockout answers through owner review", () => {
    const sponsorship = question({
      rawText: "Do you currently require sponsorship?",
      semanticType: "SPONSORSHIP_CURRENT",
      sensitive: true,
      requiresReview: true,
    });
    const result = buildPreflightAssessment({
      page: page([sponsorship]),
      profile: profile([
        fact({
          key: "current_sponsorship",
          value: "Yes",
          category: "SPONSORSHIP",
          protected: true,
        }),
      ]),
      knockoutRules: [
        {
          ruleId: "sponsorship-rule",
          semanticType: "SPONSORSHIP_CURRENT",
          disqualifyingValues: ["Yes"],
          source: "JOB_REQUIREMENT",
        },
      ],
    });

    expect(result.state).toBe("REVIEW");
    expect(result.knockoutEvaluations[0]?.state).toBe("PENDING_REVIEW");
  });

  it("blocks only an explicit disqualifying rule with a ready answer", () => {
    const relocation = question({
      rawText: "Are you willing to relocate?",
      semanticType: "RELOCATION",
    });
    const result = buildPreflightAssessment({
      page: page([relocation]),
      profile: profile([
        fact({
          key: "relocation_willingness",
          value: "No",
          category: "WORK_PREFERENCE",
        }),
      ]),
      knockoutRules: [
        {
          ruleId: "relocation-rule",
          semanticType: "RELOCATION",
          disqualifyingValues: ["No"],
          source: "JOB_REQUIREMENT",
        },
      ],
    });

    expect(result.state).toBe("BLOCKED");
    expect(result.knockoutEvaluations[0]?.state).toBe("DISQUALIFIED");
  });

  it("blocks selected contradictory evidence", () => {
    const result = buildPreflightAssessment({
      page: page([question({})]),
      profile: profile([fact({})]),
      evidenceGraph: contradictionGraph,
      selectedEvidenceIds: ["evidence-a", "evidence-b"],
    });

    expect(result.state).toBe("BLOCKED");
    expect(result.contradictionDetected).toBe(true);
    expect(result.blockingReasons).toContain(
      "Selected evidence contains an unresolved contradiction",
    );
  });
});
