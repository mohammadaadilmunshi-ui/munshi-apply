import { describe, expect, it } from "vitest";
import type { PreflightGateSummary } from "@munshi-apply/application-model";
import type { ApplicationPage, FillInstruction } from "@munshi-apply/contracts";
import {
  AutoPilotController,
  type AutoPilotControllerDependencies,
  type AutoPilotRuntimeState,
} from "./autopilot-controller";

const readyPreflight: PreflightGateSummary = {
  state: "READY",
  readyCount: 1,
  reviewCount: 0,
  unresolvedCount: 0,
  blockedCount: 0,
  canAct: true,
};

function page(jobId: string, observedAt: string): ApplicationPage {
  return {
    pageId: "page-shared-path",
    tabId: 7,
    frameId: 0,
    documentId: "document-shared-path",
    url: `https://jobs.example.test/apply?job=${jobId}`,
    title: "Application",
    observedAt,
    controls: [
      {
        controlId: "first-name",
        frameId: 0,
        kind: "TEXT",
        tagName: "input",
        name: "firstName",
        label: "First name",
        placeholder: "",
        ariaLabel: "",
        required: true,
        disabled: false,
        visible: true,
        options: [],
        multiple: false,
        autocomplete: "given-name",
        invalid: false,
        validationMessage: "",
      },
    ],
    questions: [],
    applicationState: "PERSONAL",
    pageFingerprint: `fingerprint-${jobId}-${observedAt}`,
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [],
    finalSubmissionBoundary: false,
    atsFamily: "GENERIC",
  };
}

const instruction: FillInstruction = {
  controlId: "first-name",
  frameId: 0,
  value: "Aadil",
  sensitive: false,
  approved: true,
};

describe("AutoPilot application identity isolation", () => {
  it("fails closed when the same path switches to a different explicit job query", async () => {
    let runtime: AutoPilotRuntimeState | null = null;
    let currentPage = page("123", "2026-08-17T22:00:00.000Z");
    let id = 0;

    const dependencies: AutoPilotControllerDependencies = {
      loadRuntime: async () => runtime,
      saveRuntime: async (state) => {
        runtime = state;
      },
      getPage: async () => currentPage,
      fill: async () => [
        {
          controlId: "first-name",
          status: "FILLED",
          reason: "verified",
        },
      ],
      navigate: async () => ({ status: "FAILED", reason: "unused" }),
      ensureApplication: async () => ({ created: true }),
      saveCheckpoint: async (checkpoint) => ({ created: true, checkpoint }),
      getLatestCheckpoint: async () => null,
      markDraftUsed: async () => undefined,
      now: () => "2026-08-17T22:00:01.000Z",
      randomId: () => String(++id),
      scheduleTimeout: () => undefined,
    };

    const controller = new AutoPilotController(dependencies);
    const started = await controller.start({
      tabId: 7,
      applicationId: "application-1",
      preflight: readyPreflight,
      fillInstructions: [instruction],
      selectedResumeId: null,
      selectedResumeSha256: null,
    });
    expect(started.session.status).toBe("WAITING_RESCAN");

    currentPage = page("456", "2026-08-17T22:00:02.000Z");
    const changed = await controller.onPageSnapshot(7, currentPage);

    expect(changed?.session.status).toBe("PAUSED_ERROR");
    expect(changed?.session.pauseReason).toContain("Application URL changed");
  });

  it("does not fail when only tracking parameters change", async () => {
    let runtime: AutoPilotRuntimeState | null = null;
    let currentPage = {
      ...page("123", "2026-08-17T22:00:00.000Z"),
      url: "https://jobs.example.test/apply?job=123&utm_source=a",
    };
    let id = 0;

    const dependencies: AutoPilotControllerDependencies = {
      loadRuntime: async () => runtime,
      saveRuntime: async (state) => {
        runtime = state;
      },
      getPage: async () => currentPage,
      fill: async () => [
        {
          controlId: "first-name",
          status: "FILLED",
          reason: "verified",
        },
      ],
      navigate: async () => ({ status: "FAILED", reason: "unused" }),
      ensureApplication: async () => ({ created: true }),
      saveCheckpoint: async (checkpoint) => ({ created: true, checkpoint }),
      getLatestCheckpoint: async () => null,
      markDraftUsed: async () => undefined,
      now: () => "2026-08-17T22:00:01.000Z",
      randomId: () => String(++id),
      scheduleTimeout: () => undefined,
    };

    const controller = new AutoPilotController(dependencies);
    await controller.start({
      tabId: 7,
      applicationId: "application-1",
      preflight: readyPreflight,
      fillInstructions: [instruction],
      selectedResumeId: null,
      selectedResumeSha256: null,
    });

    currentPage = {
      ...page("123", "2026-08-17T22:00:02.000Z"),
      url: "https://jobs.example.test/apply?job=123&utm_source=b",
    };
    const changed = await controller.onPageSnapshot(7, currentPage);

    expect(changed?.session.status).not.toBe("PAUSED_ERROR");
  });
});
