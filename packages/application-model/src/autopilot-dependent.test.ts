import { describe, expect, it } from "vitest";
import { planAutoPilotStep } from "./autopilot";

describe("dependent AutoPilot forms", () => {
  it("pauses instead of navigating when a new required control appears", () => {
    const plan = planAutoPilotStep({
      observation: {
        applicationId: "app-1",
        state: "QUESTIONS",
        pageId: "page-1",
        pageFingerprint: "fp-2",
        visibleControlIds: ["new-required"],
        validationErrorCount: 0,
        securityCheckpoint: null,
        canNavigateNext: true,
        isFinalSubmissionStep: false,
        unresolvedRequiredControlIds: ["new-required"],
      },
      preflight: {
        state: "READY",
        readyCount: 0,
        reviewCount: 0,
        unresolvedCount: 0,
        blockedCount: 0,
        canAct: true,
      },
      fillInstructions: [],
    });
    expect(plan.action.type).toBe("PAUSE_REVIEW");
    expect(plan.reason).toContain("Re-scan");
  });
});
