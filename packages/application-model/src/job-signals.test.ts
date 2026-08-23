import { describe, expect, it } from "vitest";
import { analyzeJobSignals } from "./job-signals";

describe("job signal intelligence", () => {
  it("keeps every dimension unknown when no job evidence is supplied", () => {
    const report = analyzeJobSignals({});
    expect(report.overallSignal).toBe("INSUFFICIENT_DATA");
    expect(report.overallScore).toBeNull();
    expect(report.signals).toHaveLength(0);
    expect(
      Object.values(report.dimensions).every((item) => item.score === null),
    ).toBe(true);
  });

  it("records explicit compensation as high clarity rather than guessing missing pay", () => {
    const report = analyzeJobSignals({
      role: "People Analytics Specialist",
      compensation: "$82,000 - $96,000 per year",
      description: "Build workforce dashboards and support people analytics.",
    });
    expect(report.dimensions.COMPENSATION_CLARITY.score).toBe(92);
    expect(report.dimensions.COMPENSATION_CLARITY.confidence).toBeGreaterThan(
      0.9,
    );
    expect(
      report.signals.some((signal) =>
        signal.evidence.includes("$82,000 - $96,000"),
      ),
    ).toBe(true);
    expect(report.overallSignal).toBe("INSUFFICIENT_DATA");
    expect(report.overallScore).toBeNull();
  });

  it("flags a junior title paired with a high explicit experience threshold", () => {
    const report = analyzeJobSignals({
      role: "HR Coordinator",
      requirements: "Candidates must have 5+ years of professional experience.",
    });
    expect(report.dimensions.QUALIFICATION_INFLATION.score).toBe(88);
    expect(report.dimensions.SENIORITY_ALIGNMENT.score).toBe(30);
    expect(
      report.signals.find(
        (signal) => signal.dimension === "QUALIFICATION_INFLATION",
      )?.explanation,
    ).toMatch(/junior-position title/i);
  });

  it("surfaces workload, schedule, and travel language as separate dimensions", () => {
    const report = analyzeJobSignals({
      description:
        "This is a high-volume environment with multiple competing priorities. Weekend work is required and the role includes up to 40% travel.",
    });
    expect(report.dimensions.WORKLOAD_PRESSURE.score).toBeGreaterThanOrEqual(
      50,
    );
    expect(report.dimensions.SCHEDULE_INTENSITY.score).toBeGreaterThanOrEqual(
      60,
    );
    expect(report.dimensions.TRAVEL_BURDEN.score).toBe(70);
    expect(
      report.signals.every((signal) => signal.evidence.trim().length > 0),
    ).toBe(true);
  });

  it("reports explicit work-authorization constraints without deciding eligibility", () => {
    const report = analyzeJobSignals({
      requirements:
        "Applicants must be authorized to work in the United States. We will not provide visa sponsorship for this position.",
    });
    expect(report.dimensions.WORK_AUTHORIZATION_RISK.score).toBe(92);
    const signal = report.signals.find(
      (candidate) => candidate.dimension === "WORK_AUTHORIZATION_RISK",
    );
    expect(signal?.evidence).toMatch(/not provide visa sponsorship/i);
    expect(signal?.explanation).toMatch(/evaluated separately/i);
  });

  it("measures observed application friction independently from employer quality", () => {
    const report = analyzeJobSignals({
      applicationFriction: {
        accountRequired: true,
        manualRequiredControls: 3,
        validationErrors: 2,
      },
    });
    expect(report.dimensions.APPLICATION_FRICTION.score).toBe(64);
    expect(report.signals[0]?.evidence).toContain("manual_required_controls=3");
    expect(report.signals[0]?.explanation).toMatch(/observed workflow/i);
  });

  it("detects broad cross-functional scope without calling the workplace toxic", () => {
    const report = analyzeJobSignals({
      description:
        "Own recruiting, people analytics, HRIS, payroll, employee relations, benefits, compliance, and project management activities.",
    });
    expect(
      report.dimensions.RESPONSIBILITY_BREADTH.score,
    ).toBeGreaterThanOrEqual(70);
    expect(
      report.signals.every((signal) => !/toxic/i.test(signal.explanation)),
    ).toBe(true);
    expect(report.disclaimer).toMatch(/do not diagnose employer culture/i);
  });

  it("does not invent a compensation or stability score when those facts are absent", () => {
    const report = analyzeJobSignals({
      role: "Analyst",
      description: "Analyze workforce data and prepare recurring reports.",
    });
    expect(report.dimensions.COMPENSATION_CLARITY.score).toBeNull();
    expect(report.dimensions.ROLE_STABILITY.score).toBeNull();
  });

  it("requires exact evidence and a direction for every scored dimension", () => {
    const report = analyzeJobSignals({
      role: "Senior HRIS Analyst",
      employmentType: "Regular full-time",
      compensation: "$90,000 to $110,000",
      requirements: "At least 5 years of HRIS experience.",
      description: "The position requires up to 10% travel.",
    });
    const scored = Object.values(report.dimensions).filter(
      (dimension) => dimension.score !== null,
    );
    expect(scored.length).toBeGreaterThanOrEqual(3);
    expect(
      scored.every(
        (dimension) =>
          dimension.confidence > 0 && dimension.evidenceIds.length > 0,
      ),
    ).toBe(true);
    expect(
      report.signals.every(
        (signal) =>
          signal.evidence.trim().length > 0 &&
          ["POSITIVE", "CONCERN", "NEUTRAL"].includes(signal.direction) &&
          ["JOB_POSTING", "APPLICATION_OBSERVATION"].includes(signal.source),
      ),
    ).toBe(true);
    expect(report.overallSignal).not.toBe("INSUFFICIENT_DATA");
  });

  it("does not reinterpret a generic sponsorship question as employer policy", () => {
    const report = analyzeJobSignals({
      description:
        "Application question: Will you now or in the future require sponsorship?",
    });
    expect(report.dimensions.WORK_AUTHORIZATION_RISK.score).toBeNull();
    expect(
      report.signals.some(
        (signal) => signal.dimension === "WORK_AUTHORIZATION_RISK",
      ),
    ).toBe(false);
  });
});
