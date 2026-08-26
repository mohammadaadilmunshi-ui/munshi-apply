import { describe, expect, it } from "vitest";
import type { ApplicationPage } from "@munshi-apply/contracts";
import type { PreflightGateSummary } from "@munshi-apply/application-model";
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

function applicationPage(): ApplicationPage {
  return {
    pageId: "page-navigation",
    tabId: 7,
    frameId: 0,
    documentId: "document-navigation",
    url: "https://jobs.example.test/apply/123",
    title: "Application",
    observedAt: "2026-08-17T21:30:00.000Z",
    controls: [],
    questions: [],
    applicationState: "QUESTIONS",
    pageFingerprint: "fingerprint-navigation",
    securityCheckpoint: null,
    validationErrorCount: 0,
    navigationCandidates: [
      {
        controlId: "next",
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

describe("AutoPilot interrupted navigation recovery", () => {
  it("pauses instead of replaying a forward action whose dispatch outcome is unknown", async () => {
    let runtime: AutoPilotRuntimeState | null = null;
    let latestCheckpoint: Awaited<
      ReturnType<AutoPilotControllerDependencies["getLatestCheckpoint"]>
    > = null;
    let navigateCount = 0;
    let id = 0;
    let clock = Date.parse("2026-08-17T21:30:01.000Z");

    const dependencies: AutoPilotControllerDependencies = {
      loadRuntime: async () => runtime,
      saveRuntime: async (state) => {
        runtime = state;
      },
      getPage: async () => applicationPage(),
      fill: async () => [],
      navigate: async () => {
        navigateCount += 1;
        throw new Error("message port closed after click");
      },
      ensureApplication: async () => ({ created: true }),
      saveCheckpoint: async (checkpoint) => {
        const created = latestCheckpoint === null;
        latestCheckpoint = checkpoint;
        return { created, checkpoint };
      },
      getLatestCheckpoint: async () => latestCheckpoint,
      markDraftUsed: async () => undefined,
      now: () => {
        const value = new Date(clock).toISOString();
        clock += 1_000;
        return value;
      },
      randomId: () => String(++id),
      scheduleTimeout: () => undefined,
    };

    const controller = new AutoPilotController(dependencies);
    const started = await controller.start({
      tabId: 7,
      applicationId: "application-1",
      preflight: readyPreflight,
      fillInstructions: [],
      selectedResumeId: null,
      selectedResumeSha256: null,
    });

    expect(started.session.status).toBe("PAUSED_REVIEW");
    expect(started.waitingFor).toBeNull();
    expect(started.actionDeadlineAt).toBeNull();
    expect(started.session.pauseReason).toContain("could not confirm");
    expect(navigateCount).toBe(1);

    const persisted =
      (await dependencies.loadRuntime()) as AutoPilotRuntimeState;
    expect(persisted.navigationDispatchAttempted).toBe(false);
    expect(persisted.beforeNavigation).toBeNull();

    const recovered = await new AutoPilotController(dependencies).recover();
    expect(recovered?.session.status).toBe("PAUSED_REVIEW");
    expect(navigateCount).toBe(1);
  });
});
