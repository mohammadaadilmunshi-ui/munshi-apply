import { describe, expect, it } from "vitest";
import { analyzeJobSignals, type JobSignalInput } from "./job-signals";

const roleFixtures: ReadonlyArray<{
  family: string;
  input: JobSignalInput;
  expectedDimensions: readonly string[];
}> = [
  {
    family: "HR",
    input: {
      role: "Human Resources Coordinator",
      employmentType: "Regular full-time",
      compensation: "$58,000 - $66,000 per year",
      description:
        "Support employee relations, benefits, compliance, recruiting, payroll, and HR operations in a high-volume environment.",
    },
    expectedDimensions: [
      "RESPONSIBILITY_BREADTH",
      "WORKLOAD_PRESSURE",
      "COMPENSATION_CLARITY",
      "ROLE_STABILITY",
    ],
  },
  {
    family: "People Analytics",
    input: {
      role: "People Analytics Analyst",
      employmentType: "Permanent",
      compensation: "$82,000 to $96,000",
      description:
        "Build workforce analytics dashboards and recurring headcount reports. The role includes up to 10% travel.",
    },
    expectedDimensions: [
      "TRAVEL_BURDEN",
      "COMPENSATION_CLARITY",
      "ROLE_STABILITY",
    ],
  },
  {
    family: "Recruiting",
    input: {
      role: "Recruiting Coordinator",
      employmentType: "Fixed-term contract role",
      compensation: "Competitive salary",
      description:
        "Coordinate a high-volume interview schedule with multiple competing priorities and weekend work as needed.",
    },
    expectedDimensions: [
      "WORKLOAD_PRESSURE",
      "SCHEDULE_INTENSITY",
      "COMPENSATION_CLARITY",
      "ROLE_STABILITY",
    ],
  },
  {
    family: "HRIS",
    input: {
      role: "Senior HRIS Analyst",
      employmentType: "Regular full-time",
      compensation: "$95,000 - $115,000",
      requirements: "Candidates need 5 years of HRIS experience.",
      description: "Maintain HRIS integrations and support payroll reporting.",
    },
    expectedDimensions: [
      "COMPENSATION_CLARITY",
      "SENIORITY_ALIGNMENT",
      "ROLE_STABILITY",
    ],
  },
  {
    family: "Operations",
    input: {
      role: "People Operations Specialist",
      employmentType: "Permanent",
      compensation: "$70,000 - $80,000",
      workArrangement: "On-site attendance is required",
      description:
        "Manage operations, payroll, benefits, compliance, and employee relations. The position requires up to 25% travel.",
    },
    expectedDimensions: [
      "RESPONSIBILITY_BREADTH",
      "TRAVEL_BURDEN",
      "COMPENSATION_CLARITY",
      "ROLE_STABILITY",
      "LOCATION_CONSTRAINTS",
    ],
  },
  {
    family: "Mixed responsibility",
    input: {
      role: "HR and Business Operations Associate",
      employmentType: "Seasonal",
      compensation: "Competitive compensation",
      description:
        "Wear many hats across recruiting, people analytics, HRIS, payroll, compliance, project management, sales, and marketing. Mandatory overtime may be required.",
    },
    expectedDimensions: [
      "ROLE_AMBIGUITY",
      "RESPONSIBILITY_BREADTH",
      "SCHEDULE_INTENSITY",
      "COMPENSATION_CLARITY",
      "ROLE_STABILITY",
    ],
  },
];

describe("Job Signal realistic role-family calibration", () => {
  for (const fixture of roleFixtures) {
    it(`keeps ${fixture.family} analysis deterministic and evidence-backed`, () => {
      const first = analyzeJobSignals(fixture.input);
      const second = analyzeJobSignals(fixture.input);
      expect(second).toEqual(first);
      for (const dimension of fixture.expectedDimensions) {
        const result =
          first.dimensions[dimension as keyof typeof first.dimensions];
        expect(result.score, dimension).not.toBeNull();
        expect(result.evidenceIds.length, dimension).toBeGreaterThan(0);
      }
      expect(first.overallSignal).not.toBe("INSUFFICIENT_DATA");
      expect(first.disclaimer).toMatch(/do not prove.*caused/i);
      expect(
        first.signals.every(
          (signal) =>
            !/toxic|recruiter identity|employer intent/i.test(
              `${signal.evidence} ${signal.explanation}`,
            ),
        ),
      ).toBe(true);
    });
  }
});
