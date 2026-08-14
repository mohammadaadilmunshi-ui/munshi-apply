import { describe, expect, it } from "vitest";
import type {
  ApplicationPage,
  FillInstruction,
} from "@munshi-apply/contracts";
import type { PreflightGateSummary } from "@munshi-apply/application-model";
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

const reviewPreflight: PreflightGateSummary = {
  state: "REVIEW",
  readyCount: 0,
  reviewCount: 1,
  unresolvedCount: 0,
  blockedCount: 0,
  canAct: false,
};

function control(controlId: string) {
  return {
    controlId,
    frameId: 0,
    kind: "TEXT" as const,
    tagName: "input",
    name: controlId,
    label: controlId,
    placeholder: "",
    ariaLabel: "",
    required: false,
    disabled: false,
    visible: true,
    options: [],
    multiple: false,
    autocomplete: "",
    invalid: false,
    validationMessage: "",
  };
}

function page(input?: {
  url?: string;
  observedAt?: string;
  controls?: string[];
  navigation?: boolean;
  securityCheckpoint?: "MFA" | null;
  final?: boolean;
  validationErrorCount?: number;
  pageId?: string;
  pageFingerprint?: string;
}): ApplicationPage {
  return {
    pageId: input?.pageId ?? "page-1",
    tabId: 7,
    frameId: 0,
    documentId: `document-${input?.pageId ?? "1"}`,
    url: input?.url ?? "https://jobs.example.com/apply/123",
    title: "Application",
    observedAt: input?.observedAt ?? "2026-08-14T21:00:00.000Z",
    controls: (input?.controls ?? []).map(control),
    questions: [],
    applicationState: input?.final ? "SUBMISSION" : "PERSONAL",
    pageFingerprint: input?.pageFingerprint ?? "fingerprint-1",
    securityCheckpoint: input?.securityCheckpoint ?? null,
    validationErrorCount: input?.validationErrorCount ?? 0,
    navigationCandidates: input?.navigation
      ? [
          {
            controlId: "next",
            frameId: 0,
            action: "NEXT",
            label: "Continue",
            disabled: false,
          },
        ]
      : [],
    finalSubmissionBoundary: input?.final ?? false,
  };
}

function instruction(controlId: string): FillInstruction {
  return {
    controlId,
    frameId: 0,
    value: `value-${controlId}`,
    sensitive: false,
    approved: true,
  };
}

type HarnessOptions = {
  checkpointMode?: "success" | "fail" | "lost-first";
  navigationChangesPage?: boolean;
};

function harness(initialPage: ApplicationPage, options: HarnessOptions = {}) {
  let runtime: AutoPilotRuntimeState | null = null;
  let currentPage = initialPage;
  let latestCheckpoint: Awaited<
    ReturnType<AutoPilotControllerDependencies["getLatestCheckpoint"]>
  > = null;
  let checkpointAttempts = 0;
  let fillCount = 0;
  let navigateCount = 0;
  let id = 0;
  let clock = Date.parse("2026-08-14T21:00:01.000Z");
  const events: string[] = [];

  const dependencies: AutoPilotControllerDependencies = {
    loadRuntime: async () => runtime,
    saveRuntime: async (state) => {
      runtime = state;
    },
    getPage: async () => currentPage,
    fill: async (_tabId, item) => {
      fillCount += 1;
      events.push(`fill:${item.controlId}`);
      return [
        {
          controlId: item.controlId,
          status: "FILLED",
          reason: "verified",
        },
      ];
    },
    navigate: async () => {
      navigateCount += 1;
      events.push("navigate");
      if (options.navigationChangesPage) {
        currentPage = page({
          url: "https://jobs.example.com/apply/123/step-2",
          observedAt: "2026-08-14T22:00:00.000Z",
          pageId: "page-2",
          pageFingerprint: "fingerprint-2",
        });
      }
      return {
        status: "NAVIGATED",
        reason: "verified safe navigation",
      };
    },
    ensureApplication: async () => {
      events.push("ensure-application");
      return { created: true };
    },
    saveCheckpoint: async (checkpoint) => {
      checkpointAttempts += 1;
      events.push(`checkpoint:${checkpoint.sequence}`);
      if (options.checkpointMode === "fail") {
        throw new Error("native unavailable");
      }
      if (
        options.checkpointMode === "lost-first" &&
        checkpointAttempts === 1
      ) {
        latestCheckpoint = checkpoint;
        throw new Error("response lost");
      }
      const created = latestCheckpoint === null;
      latestCheckpoint = checkpoint;
      return { created, checkpoint };
    },
    getLatestCheckpoint: async () => latestCheckpoint,
    now: () => {
      const value = new Date(clock).toISOString();
      clock += 1_000;
      return value;
    },
    randomId: () => String(++id),
    scheduleTimeout: () => undefined,
  };

  return {
    dependencies,
    controller: new AutoPilotController(dependencies),
    setPage(next: ApplicationPage) {
      currentPage = next;
    },
    newController() {
      return new AutoPilotController(dependencies);
    },
    runtime() {
      return runtime;
    },
    events,
    counts() {
      return { fillCount, navigateCount, checkpointAttempts };
    },
  };
}

function startInput(
  fillInstructions: FillInstruction[] = [],
  preflight: PreflightGateSummary = readyPreflight,
) {
  return {
    tabId: 7,
    applicationId: "app-1",
    preflight,
    fillInstructions,
    selectedResumeId: null,
    selectedResumeSha256: null,
  };
}

describe("persistent AutoPilot controller", () => {
  it("runs exactly one verified fill before requiring a fresh rescan", async () => {
    const test = harness(page({ controls: ["first", "last"] }));

    const started = await test.controller.start(
      startInput([instruction("first"), instruction("last")]),
    );

    expect(started.session.status).toBe("WAITING_RESCAN");
    expect(started.waitingFor).toBe("FILL");
    expect(started.session.completedControlIds).toEqual(["first"]);
    expect(test.counts().fillCount).toBe(1);

    const fresh = page({
      controls: ["first", "last"],
      observedAt: "2026-08-14T22:00:00.000Z",
    });
    test.setPage(fresh);
    const afterRescan = await test.controller.onPageSnapshot(7, fresh);

    expect(afterRescan?.session.status).toBe("WAITING_RESCAN");
    expect(afterRescan?.session.completedControlIds).toEqual([
      "first",
      "last",
    ]);
    expect(test.counts().fillCount).toBe(2);
  });

  it("persists and acknowledges a checkpoint before navigation dispatch", async () => {
    const test = harness(page({ navigation: true }));

    const status = await test.controller.start(startInput());

    expect(status.session.status).toBe("WAITING_RESCAN");
    expect(status.waitingFor).toBe("NAVIGATION");
    expect(test.events.indexOf("checkpoint:0")).toBeGreaterThanOrEqual(0);
    expect(test.events.indexOf("navigate")).toBeGreaterThan(
      test.events.indexOf("checkpoint:0"),
    );
  });

  it("never navigates when the durable checkpoint cannot be saved", async () => {
    const test = harness(page({ navigation: true }), {
      checkpointMode: "fail",
    });

    const status = await test.controller.start(startInput());

    expect(status.session.status).toBe("PAUSED_ERROR");
    expect(status.session.pauseReason).toMatch(/checkpoint/i);
    expect(test.counts().checkpointAttempts).toBe(2);
    expect(test.counts().navigateCount).toBe(0);
  });

  it("retries the exact checkpoint when the first acknowledgement is lost", async () => {
    const test = harness(page({ navigation: true }), {
      checkpointMode: "lost-first",
    });

    const status = await test.controller.start(startInput());

    expect(status.session.status).toBe("WAITING_RESCAN");
    expect(test.counts().checkpointAttempts).toBe(2);
    expect(test.counts().navigateCount).toBe(1);
  });

  it("pauses at security, final submission, and pre-flight review boundaries", async () => {
    const security = harness(page({ securityCheckpoint: "MFA" }));
    const securityStatus = await security.controller.start(startInput());
    expect(securityStatus.session.status).toBe("PAUSED_SECURITY");
    expect(security.counts().fillCount).toBe(0);
    expect(security.counts().navigateCount).toBe(0);

    const final = harness(page({ final: true, navigation: true }));
    const finalStatus = await final.controller.start(startInput());
    expect(finalStatus.session.status).toBe("PAUSED_FINAL");
    expect(final.counts().navigateCount).toBe(0);

    const review = harness(page({ controls: ["first"] }));
    const reviewStatus = await review.controller.start(
      startInput([instruction("first")], reviewPreflight),
    );
    expect(reviewStatus.session.status).toBe("PAUSED_REVIEW");
    expect(review.counts().fillCount).toBe(0);
  });

  it("recovers a post-fill wait only from a fresh page observation", async () => {
    const test = harness(page({ controls: ["first"] }));
    await test.controller.start(startInput([instruction("first")]));
    expect(test.counts().fillCount).toBe(1);

    const staleRecovery = await test.newController().recover();
    expect(staleRecovery?.session.status).toBe("WAITING_RESCAN");
    expect(test.counts().fillCount).toBe(1);

    const fresh = page({
      controls: ["first"],
      observedAt: "2026-08-14T22:00:00.000Z",
    });
    test.setPage(fresh);
    const recovered = await test.newController().recover();

    expect(recovered?.session.status).toBe("RUNNING");
    expect(recovered?.waitingFor).toBe(null);
    expect(test.counts().fillCount).toBe(1);
  });

  it("reconciles navigation after service-worker suspension without clicking twice", async () => {
    const test = harness(page({ navigation: true }), {
      navigationChangesPage: true,
    });
    const started = await test.controller.start(startInput());
    expect(started.waitingFor).toBe("NAVIGATION");
    expect(test.counts().navigateCount).toBe(1);

    const recovered = await test.newController().recover();

    expect(recovered?.session.status).toBe("RUNNING");
    expect(recovered?.waitingFor).toBe(null);
    expect(recovered?.lastUrl).toContain("/step-2");
    expect(test.counts().navigateCount).toBe(1);
  });

  it("fails closed when the application URL changes without verified navigation", async () => {
    const test = harness(page());
    const started = await test.controller.start(startInput());
    expect(started.session.status).toBe("RUNNING");

    test.setPage(
      page({
        url: "https://jobs.example.com/apply/another-job",
        observedAt: "2026-08-14T22:00:00.000Z",
      }),
    );
    const recovered = await test.newController().recover();

    expect(recovered?.session.status).toBe("PAUSED_ERROR");
    expect(recovered?.session.pauseReason).toMatch(/URL changed/i);
  });

  it("keeps an owner stop durable across service-worker recovery", async () => {
    const test = harness(page({ controls: ["first"] }));
    await test.controller.start(startInput([instruction("first")]));
    const stopped = await test.controller.stop("Owner stopped AutoPilot");
    expect(stopped?.session.status).toBe("STOPPED");
    const fillCount = test.counts().fillCount;

    const recovered = await test.newController().recover();

    expect(recovered?.session.status).toBe("STOPPED");
    expect(test.counts().fillCount).toBe(fillCount);
  });
});
