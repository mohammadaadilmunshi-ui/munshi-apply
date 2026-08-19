import { describe, expect, it } from "vitest";
import {
  assignExperimentVariant,
  summarizeExperiment,
  validateOpaqueAttributionToken,
  type ExperimentDefinition,
} from "./analytics";

const experiment: ExperimentDefinition = {
  experimentId: "resume-layout",
  label: "Resume layout test",
  variants: [
    { variantId: "a", label: "A", weight: 1 },
    { variantId: "b", label: "B", weight: 1 },
  ],
  minimumSamplePerVariant: 2,
  status: "ACTIVE",
};

describe("assignExperimentVariant", () => {
  it("assigns the same subject deterministically for the same salt", () => {
    const first = assignExperimentVariant({
      experiment,
      subjectId: "application-1",
      assignmentSalt: "private-salt",
    });
    const second = assignExperimentVariant({
      experiment,
      subjectId: "application-1",
      assignmentSalt: "private-salt",
    });
    expect(second).toEqual(first);
  });

  it("refuses assignments to inactive experiments", () => {
    expect(() =>
      assignExperimentVariant({
        experiment: { ...experiment, status: "DRAFT" },
        subjectId: "application-1",
        assignmentSalt: "private-salt",
      }),
    ).toThrow("must be active");
  });
});

describe("summarizeExperiment", () => {
  it("does not call a variant a winner before minimum sample gates", () => {
    const summary = summarizeExperiment({
      experiment,
      assignments: [
        {
          experimentId: experiment.experimentId,
          subjectId: "app-1",
          variantId: "a",
        },
        {
          experimentId: experiment.experimentId,
          subjectId: "app-2",
          variantId: "b",
        },
      ],
      outcomesBySubject: new Map([
        [
          "app-1",
          [
            {
              eventId: "o-1",
              applicationId: "app-1",
              stage: "INTERVIEW",
              occurredAt: "2026-08-14T18:00:00.000Z",
              source: "owner-confirmed",
            },
          ],
        ],
      ]),
    });

    expect(summary.analysisReady).toBe(false);
    expect(summary.reason).toContain("do not label a variant a winner");
  });

  it("reports descriptive rates only after every variant reaches the sample gate", () => {
    const summary = summarizeExperiment({
      experiment,
      assignments: [
        {
          experimentId: experiment.experimentId,
          subjectId: "a1",
          variantId: "a",
        },
        {
          experimentId: experiment.experimentId,
          subjectId: "a2",
          variantId: "a",
        },
        {
          experimentId: experiment.experimentId,
          subjectId: "b1",
          variantId: "b",
        },
        {
          experimentId: experiment.experimentId,
          subjectId: "b2",
          variantId: "b",
        },
      ],
      outcomesBySubject: new Map([
        [
          "a1",
          [
            {
              eventId: "o-1",
              applicationId: "a1",
              stage: "INTERVIEW",
              occurredAt: "2026-08-14T18:00:00.000Z",
              source: "owner-confirmed",
            },
          ],
        ],
      ]),
    });

    expect(summary.analysisReady).toBe(true);
    expect(
      summary.variants.find((variant) => variant.variantId === "a")
        ?.positiveOutcomeRate,
    ).toBe(0.5);
    expect(
      summary.variants.find((variant) => variant.variantId === "b")
        ?.positiveOutcomeRate,
    ).toBe(0);
    expect(summary.reason).toContain("without implying causality");
  });
});

describe("validateOpaqueAttributionToken", () => {
  it("accepts opaque non-semantic tokens and rejects unsafe short or punctuated values", () => {
    expect(validateOpaqueAttributionToken("7KQ2N9X4_abcd")).toBe(true);
    expect(validateOpaqueAttributionToken("short")).toBe(false);
    expect(validateOpaqueAttributionToken("job=secret")).toBe(false);
  });
});
