import { describe, expect, it } from "vitest";
import { analyzeJobSignals } from "@munshi-apply/application-model";
import { buildJobSignalView, jobSignalDisposition } from "./job-signal-view";

describe("Job Signal presentation model", () => {
  it("treats high compensation clarity as positive but high sponsorship risk as concern", () => {
    expect(jobSignalDisposition("COMPENSATION_CLARITY", 92)).toBe("POSITIVE");
    expect(jobSignalDisposition("WORK_AUTHORIZATION_RISK", 92)).toBe("CONCERN");
  });

  it("keeps missing evidence explicitly unknown", () => {
    const view = buildJobSignalView({
      report: analyzeJobSignals({}),
      preflightState: "READY",
    });
    expect(view.overallLabel).toBe("Insufficient evidence");
    expect(view.knownDimensionCount).toBe(0);
    expect(view.unknownDimensionCount).toBe(12);
    expect(view.opportunity.priority).toBe("INSUFFICIENT_DATA");
  });

  it("links dimension rows to the exact evidence and explanations that produced them", () => {
    const report = analyzeJobSignals({
      compensation: "$75,000 - $88,000",
      requirements: "We will not provide visa sponsorship for this position.",
      description: "The role requires up to 40% travel.",
    });
    const view = buildJobSignalView({ report, preflightState: "REVIEW" });

    const compensation = view.rows.find(
      (row) => row.dimension === "COMPENSATION_CLARITY",
    );
    const authorization = view.rows.find(
      (row) => row.dimension === "WORK_AUTHORIZATION_RISK",
    );
    const travel = view.rows.find((row) => row.dimension === "TRAVEL_BURDEN");

    expect(compensation?.disposition).toBe("POSITIVE");
    expect(compensation?.evidence[0]).toContain("$75,000 - $88,000");
    expect(authorization?.disposition).toBe("CONCERN");
    expect(authorization?.explanations[0]).toMatch(
      /eligibility is evaluated separately/i,
    );
    expect(travel?.score).toBe(70);
    expect(travel?.evidence[0]).toMatch(/40% travel/i);
  });
});
