import { describe, expect, it } from "vitest";
import { analyzeJobSignals } from "./job-signals";
import { assessJobOpportunity } from "./job-opportunity";

function lowConcernSignals() {
  return analyzeJobSignals({
    role: "People Analytics Associate",
    compensation: "$72,000 - $82,000 per year",
    employmentType: "regular full-time",
    description: "Analyze workforce data and build recurring dashboards.",
  });
}

describe("job opportunity prioritization", () => {
  it("returns insufficient data instead of treating a clean posting as candidate fit", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "READY",
    });
    expect(assessment.priority).toBe("INSUFFICIENT_DATA");
    expect(assessment.priorityScore).toBeNull();
    expect(assessment.unknowns).toContain(
      "Role-family fit has not been evaluated from verified evidence.",
    );
  });

  it("prioritizes a strong verified fit with low posting concern", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "READY",
      fit: {
        roleMatchScore: 94,
        evidenceMatchScore: 91,
        locationCompatibility: "MATCH",
        workAuthorizationCompatibility: "MATCH",
        compensationCompatibility: "MATCH",
      },
    });
    expect(assessment.priority).toBe("HIGH");
    expect(assessment.priorityScore).toBeGreaterThanOrEqual(72);
    expect(assessment.positiveFactors.length).toBeGreaterThan(2);
  });

  it("holds on deterministic pre-flight blocking facts regardless of fit", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "BLOCKED",
      fit: {
        roleMatchScore: 100,
        evidenceMatchScore: 100,
        locationCompatibility: "MATCH",
        workAuthorizationCompatibility: "MATCH",
        compensationCompatibility: "MATCH",
      },
    });
    expect(assessment.priority).toBe("HOLD");
    expect(assessment.priorityScore).toBe(0);
    expect(assessment.explanation).toMatch(/verified contradiction/i);
  });

  it("holds consequential unresolved pre-flight instead of manufacturing a score", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "UNRESOLVED",
      fit: {
        roleMatchScore: 90,
        evidenceMatchScore: 90,
      },
    });
    expect(assessment.priority).toBe("HOLD");
    expect(assessment.priorityScore).toBeNull();
    expect(assessment.explanation).toMatch(/does not guess eligibility/i);
  });

  it("holds an explicit work-authorization mismatch even when other fit is strong", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "READY",
      fit: {
        roleMatchScore: 95,
        evidenceMatchScore: 95,
        locationCompatibility: "MATCH",
        workAuthorizationCompatibility: "MISMATCH",
        compensationCompatibility: "MATCH",
      },
    });
    expect(assessment.priority).toBe("HOLD");
    expect(assessment.priorityScore).toBe(0);
    expect(assessment.riskFactors[0]).toMatch(/work-authorization/i);
  });

  it("holds explicit sponsorship risk when owner compatibility is unknown", () => {
    const signals = analyzeJobSignals({
      role: "HR Analyst",
      requirements: "We will not provide visa sponsorship for this position.",
    });
    const assessment = assessJobOpportunity({
      jobSignals: signals,
      preflightState: "REVIEW",
      fit: {
        roleMatchScore: 88,
        evidenceMatchScore: 82,
        workAuthorizationCompatibility: "UNKNOWN",
      },
    });
    expect(assessment.priority).toBe("HOLD");
    expect(assessment.priorityScore).toBeNull();
    expect(assessment.explanation).toMatch(/work-authorization review/i);
  });

  it("penalizes evidence-backed job concerns without treating them as employer diagnoses", () => {
    const signals = analyzeJobSignals({
      role: "HR Coordinator",
      requirements: "Candidates must have 5+ years of experience.",
      description:
        "High-volume role with mandatory overtime, evenings and weekends, and up to 60% travel.",
    });
    const assessment = assessJobOpportunity({
      jobSignals: signals,
      preflightState: "READY",
      fit: {
        roleMatchScore: 80,
        evidenceMatchScore: 80,
        locationCompatibility: "MATCH",
        workAuthorizationCompatibility: "MATCH",
      },
    });
    expect(assessment.priorityScore).not.toBeNull();
    expect(assessment.riskFactors.some((item) => /Job Signal concern/i.test(item))).toBe(
      true,
    );
    expect(assessment.explanation).not.toMatch(/toxic/i);
  });

  it("keeps REVIEW opportunities rankable while preserving the owner-review warning", () => {
    const assessment = assessJobOpportunity({
      jobSignals: lowConcernSignals(),
      preflightState: "REVIEW",
      fit: {
        roleMatchScore: 88,
        evidenceMatchScore: 84,
        locationCompatibility: "MATCH",
        workAuthorizationCompatibility: "MATCH",
        compensationCompatibility: "PARTIAL",
      },
    });
    expect(["HIGH", "MEDIUM", "LOW"]).toContain(assessment.priority);
    expect(assessment.riskFactors.some((item) => /owner review/i.test(item))).toBe(
      true,
    );
  });

  it("validates score ranges instead of silently clamping invalid fit inputs", () => {
    expect(() =>
      assessJobOpportunity({
        jobSignals: lowConcernSignals(),
        preflightState: "READY",
        fit: { roleMatchScore: 120 },
      }),
    ).toThrow(/0 to 100/);
  });
});
