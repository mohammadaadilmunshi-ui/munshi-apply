import { describe, expect, it } from "vitest";
import type {
  JobSignalDimension,
  JobSignalDimensionResult,
} from "@munshi-apply/application-model";
import { parsePersistedJobSignalReport } from "./native-job-signals";

function dimension(
  name: JobSignalDimension,
  score: number | null = null,
  confidence = 0,
  evidenceIds: string[] = [],
): JobSignalDimensionResult {
  return { dimension: name, score, confidence, evidenceIds };
}

function validReport() {
  return {
    reportId: "report-1",
    applicationId: "application-1",
    jobId: "job-1",
    sourceIdentity: "https://jobs.example.com/job/1",
    sourceFingerprint: "source-1",
    evaluatedAt: "2026-08-17T20:30:00.000Z",
    overallSignal: "MODERATE",
    overallScore: 41,
    dimensions: {
      ROLE_AMBIGUITY: dimension("ROLE_AMBIGUITY"),
      RESPONSIBILITY_BREADTH: dimension("RESPONSIBILITY_BREADTH"),
      QUALIFICATION_INFLATION: dimension("QUALIFICATION_INFLATION"),
      WORKLOAD_PRESSURE: dimension("WORKLOAD_PRESSURE"),
      SCHEDULE_INTENSITY: dimension("SCHEDULE_INTENSITY"),
      TRAVEL_BURDEN: dimension("TRAVEL_BURDEN", 70, 0.98, ["signal-travel"]),
      COMPENSATION_CLARITY: dimension("COMPENSATION_CLARITY"),
      SENIORITY_ALIGNMENT: dimension("SENIORITY_ALIGNMENT"),
      ROLE_STABILITY: dimension("ROLE_STABILITY"),
      LOCATION_CONSTRAINTS: dimension("LOCATION_CONSTRAINTS"),
      WORK_AUTHORIZATION_RISK: dimension("WORK_AUTHORIZATION_RISK"),
      APPLICATION_FRICTION: dimension("APPLICATION_FRICTION"),
    },
    signals: [
      {
        signalId: "signal-travel",
        dimension: "TRAVEL_BURDEN",
        severity: "HIGH",
        direction: "CONCERN",
        source: "JOB_POSTING",
        evidence: "Up to 40% travel",
        explanation: "The posting explicitly states a 40% travel expectation.",
      },
    ],
  };
}

describe("native Job Signal parsing", () => {
  it("accepts the complete persisted evidence contract", () => {
    const parsed = parsePersistedJobSignalReport(validReport());
    expect(parsed.reportId).toBe("report-1");
    expect(parsed.overallScore).toBe(41);
    expect(parsed.dimensions.TRAVEL_BURDEN.score).toBe(70);
    expect(parsed.signals[0]?.signalId).toBe("signal-travel");
  });

  it("rejects incomplete dimension ontologies", () => {
    const candidate = validReport();
    const dimensions: Record<string, unknown> = { ...candidate.dimensions };
    delete dimensions.ROLE_AMBIGUITY;
    expect(() =>
      parsePersistedJobSignalReport({ ...candidate, dimensions }),
    ).toThrow(/complete canonical ontology/);
  });

  it("rejects cross-dimension or unreferenced evidence", () => {
    const candidate = validReport();
    expect(() =>
      parsePersistedJobSignalReport({
        ...candidate,
        dimensions: {
          ...candidate.dimensions,
          TRAVEL_BURDEN: dimension("TRAVEL_BURDEN", 70, 0.98, [
            "signal-travel",
          ]),
          WORKLOAD_PRESSURE: dimension("WORKLOAD_PRESSURE", 58, 0.9, [
            "signal-travel",
          ]),
        },
      }),
    ).toThrow(/evidence links are inconsistent/);
  });

  it("rejects invalid score state and timezone-less persistence timestamps", () => {
    const candidate = validReport();
    expect(() =>
      parsePersistedJobSignalReport({
        ...candidate,
        overallSignal: "INSUFFICIENT_DATA",
      }),
    ).toThrow(/must not include a score/);
    expect(() =>
      parsePersistedJobSignalReport({
        ...candidate,
        evaluatedAt: "2026-08-17T20:30:00",
      }),
    ).toThrow(/timezone-aware ISO timestamp/);
  });

  it("rejects malformed dimension bounds", () => {
    const candidate = validReport();
    expect(() =>
      parsePersistedJobSignalReport({
        ...candidate,
        dimensions: {
          ...candidate.dimensions,
          TRAVEL_BURDEN: dimension("TRAVEL_BURDEN", 101, 0.98, [
            "signal-travel",
          ]),
        },
      }),
    ).toThrow(/integer from 0 to 100/);
  });

  it("rejects scored dimensions that have no exact evidence", () => {
    const candidate = validReport();
    expect(() =>
      parsePersistedJobSignalReport({
        ...candidate,
        dimensions: {
          ...candidate.dimensions,
          TRAVEL_BURDEN: dimension("TRAVEL_BURDEN", 70, 0.98),
        },
        signals: [],
      }),
    ).toThrow(/requires evidence and confidence/);
  });
});
