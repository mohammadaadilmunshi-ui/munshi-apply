import { describe, expect, it, vi } from "vitest";
import type { PreflightGateSummary } from "@munshi-apply/application-model";
import type { ApplicationPage, Control } from "@munshi-apply/contracts";
import {
  AutoPilotController,
  type AutoPilotControllerDependencies,
  type AutoPilotRuntimeState,
} from "./autopilot-controller";

const readyPreflight: PreflightGateSummary = {
  state: "READY",
  readyCount: 0,
  reviewCount: 0,
  unresolvedCount: 0,
  blockedCount: 0,
  canAct: true,
};

const resumeDigest = "a".repeat(64);

function resumeControl(fileSha256: string): Control {
  return {
    controlId: "resume-file",
    frameId: 0,
    kind: "FILE",
    tagName: "input",
    name: "resume",
    label: "Upload résumé",
    placeholder: "",
    ariaLabel: "",
    required: true,
    disabled: false,
    visible: true,
    options: [],
    multiple: false,
    autocomplete: "",
    invalid: false,
    validationMessage: "",
    fileSelected: true,
    fileFingerprintState: "READY",
    fileSha256,
  };
}

function page(
  input: {
    applicationState?: ApplicationPage["applicationState"];
    controls?: Control[];
  } = {},
): ApplicationPage {
  return {
    pageId: "page-navigation-safety",
    tabId: 7,
    frameId: 0,
    documentId: "document-navigation-safety",
    url: "https://jobs.example.test/apply/123",
    title: "Application",
    pageContext: "Application",
    observedAt: "2026-08-17T22:15:00.000Z",
    controls: input.controls ?? [],
    questions: [],
    applicationState: input.applicationState ?? "QUESTIONS",
    pageFingerprint: "fingerprint-navigation-safety",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [
      {
        controlId: "continue",
        frameId: 0,
        action: "NEXT",
        label: "Continue",
        disabled: false,
      },
    ],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

function harness(currentPage: ApplicationPage) {
  let runtime: AutoPilotRuntimeState | null = null;
  let checkpointSequence = 0;
  const navigate = vi.fn().mockResolvedValue({
    status: "NAVIGATED" as const,
    reason: "verified",
  });
  const dependencies: AutoPilotControllerDependencies = {
    loadRuntime: async () => runtime,
    saveRuntime: async (state) => {
      runtime = state;
    },
    getPage: async () => currentPage,
    fill: async () => [],
    navigate,
    ensureApplication: async () => ({ created: true }),
    saveCheckpoint: async (checkpoint) => ({
      created: checkpointSequence++ === 0,
      checkpoint,
    }),
    getLatestCheckpoint: async () => null,
    markDraftUsed: async () => undefined,
    now: () => "2026-08-17T22:15:01.000Z",
    randomId: () => "navigation-safety",
    scheduleTimeout: () => undefined,
  };
  return {
    controller: new AutoPilotController(dependencies),
    navigate,
  };
}

describe("AutoPilot forward navigation safety integration", () => {
  it("does not click a generic Continue control while the employer page is in REVIEW state", async () => {
    const test = harness(page({ applicationState: "REVIEW" }));

    const status = await test.controller.start({
      tabId: 7,
      applicationId: "application-review",
      preflight: readyPreflight,
      fillInstructions: [],
      selectedResumeId: null,
      selectedResumeSha256: null,
    });

    expect(status.session.status).toBe("PAUSED_REVIEW");
    expect(status.session.pauseReason).toContain("application review state");
    expect(test.navigate).not.toHaveBeenCalled();
  });

  it("does not navigate when the employer résumé field contains a different verified file", async () => {
    const test = harness(
      page({
        applicationState: "DOCUMENTS",
        controls: [resumeControl("b".repeat(64))],
      }),
    );

    const status = await test.controller.start({
      tabId: 7,
      applicationId: "application-resume",
      preflight: readyPreflight,
      fillInstructions: [],
      selectedResumeId: "resume-1",
      selectedResumeSha256: resumeDigest,
    });

    expect(status.session.status).toBe("PAUSED_REVIEW");
    expect(status.session.pauseReason).toContain("does not match");
    expect(test.navigate).not.toHaveBeenCalled();
  });
});
