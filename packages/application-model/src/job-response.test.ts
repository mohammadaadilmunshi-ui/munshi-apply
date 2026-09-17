import { describe, expect, it } from "vitest";
import { classifyJobResponseIntent, planJobResponse } from "./job-response";

describe("job response planning", () => {
  it("uses strong reasoning for behavioral and transition answers", () => {
    expect(
      classifyJobResponseIntent(
        "Tell us about a time you handled a difficult stakeholder",
        "BEHAVIORAL_EXAMPLE",
      ),
    ).toBe("BEHAVIORAL");
    expect(
      planJobResponse(
        "Why are you leaving your current employer?",
        "CAREER_GOALS",
      ).modelLane,
    ).toBe("STRONG");
  });
  it("requires both job and candidate evidence for why-role", () => {
    const plan = planJobResponse("Why this role?", "WHY_ROLE");
    expect(plan.requiresJobContext).toBe(true);
    expect(plan.requiresCandidateEvidence).toBe(true);
  });
});
