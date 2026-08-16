import { describe, expect, it } from "vitest";
import {
  createAutoPilotCheckpoint,
  type AutoPilotObservation,
} from "./autopilot";
import {
  createAutoPilotSession,
  deriveApplicationIdentity,
  parseAutoPilotSession,
  prepareSessionCheckpoint,
  reduceAutoPilotSession,
  restoreSessionFromCheckpoint,
} from "./autopilot-session";

const observation: AutoPilotObservation = {
  applicationId: "app-1",
  state: "PERSONAL",
  pageId: "page-1",
  pageFingerprint: "fingerprint-1",
  visibleControlIds: ["control-1"],
  validationErrorCount: 0,
  securityCheckpoint: null,
  canNavigateNext: true,
  isFinalSubmissionStep: false,
};

function freshSession() {
  return createAutoPilotSession({
    sessionId: "session-1",
    applicationId: "app-1",
    applicationIdentity: deriveApplicationIdentity({
      url: "https://jobs.example.com/apply/123?utm_source=test#section",
      externalJobId: "123",
    }),
    selectedResumeId: "resume-1",
    selectedResumeSha256: "a".repeat(64),
    createdAt: "2026-08-14T21:00:00.000Z",
  });
}

describe("AutoPilot session model", () => {
  it("derives stable application identity without tracking query or hash", () => {
    const first = deriveApplicationIdentity({
      url: "https://jobs.example.com/apply/123?utm_source=a#top",
      externalJobId: "job-123",
    });
    const second = deriveApplicationIdentity({
      url: "https://jobs.example.com/apply/123?utm_source=b#bottom",
      externalJobId: "job-123",
    });
    expect(first).toBe(second);
  });

  it("is versioned and rejects corrupted resume/session state", () => {
    const session = freshSession();
    expect(session.schemaVersion).toBe(1);
    expect(() =>
      parseAutoPilotSession({
        ...session,
        selectedResumeSha256: null,
      }),
    ).toThrow(/stored together/);
  });

  it("moves one verified fill into a mandatory rescan", () => {
    const started = reduceAutoPilotSession(freshSession(), {
      type: "START",
      observation,
      at: "2026-08-14T21:00:01.000Z",
    });
    const filled = reduceAutoPilotSession(started, {
      type: "FILL_VERIFIED",
      controlId: "control-1",
      pendingControlIds: ["control-2"],
      at: "2026-08-14T21:00:02.000Z",
    });
    expect(filled.status).toBe("WAITING_RESCAN");
    expect(filled.completedControlIds).toEqual(["control-1"]);
    expect(filled.pendingControlIds).toEqual(["control-2"]);
  });

  it("requires a persisted checkpoint before navigation dispatch", () => {
    const started = reduceAutoPilotSession(freshSession(), {
      type: "START",
      observation,
      at: "2026-08-14T21:00:01.000Z",
    });
    const refused = reduceAutoPilotSession(started, {
      type: "NAVIGATION_DISPATCHED",
      at: "2026-08-14T21:00:02.000Z",
    });
    expect(refused.status).toBe("PAUSED_ERROR");

    const checkpoint = prepareSessionCheckpoint({
      session: started,
      checkpointId: "cp-0",
      observation,
      createdAt: "2026-08-14T21:00:02.000Z",
    });
    const armed = reduceAutoPilotSession(started, {
      type: "CHECKPOINT_SAVED",
      checkpoint,
      purpose: "NAVIGATION",
      at: "2026-08-14T21:00:03.000Z",
    });
    expect(armed.status).toBe("WAITING_NAVIGATION");
    expect(
      reduceAutoPilotSession(armed, {
        type: "NAVIGATION_DISPATCHED",
        at: "2026-08-14T21:00:04.000Z",
      }).status,
    ).toBe("WAITING_RESCAN");
  });

  it("pauses on security/final boundaries but lets incomplete-form validation reach the step planner", () => {
    const session = freshSession();
    expect(
      reduceAutoPilotSession(session, {
        type: "START",
        observation: { ...observation, securityCheckpoint: "MFA" },
        at: "2026-08-14T21:00:01.000Z",
      }).status,
    ).toBe("PAUSED_SECURITY");
    expect(
      reduceAutoPilotSession(session, {
        type: "START",
        observation: { ...observation, validationErrorCount: 1 },
        at: "2026-08-14T21:00:01.000Z",
      }).status,
    ).toBe("RUNNING");
    expect(
      reduceAutoPilotSession(session, {
        type: "START",
        observation: {
          ...observation,
          state: "SUBMISSION",
          isFinalSubmissionStep: true,
        },
        at: "2026-08-14T21:00:01.000Z",
      }).status,
    ).toBe("PAUSED_FINAL");
    expect(
      reduceAutoPilotSession(session, {
        type: "START",
        observation: { ...observation, applicationId: "other-app" },
        at: "2026-08-14T21:00:01.000Z",
      }).status,
    ).toBe("PAUSED_ERROR");
  });

  it("restores only a compatible checkpoint for the same application", () => {
    const checkpoint = createAutoPilotCheckpoint({
      checkpointId: "cp-2",
      observation,
      sequence: 2,
      completedControlIds: ["control-1"],
      pendingControlIds: ["control-2"],
      selectedResumeId: "resume-1",
      selectedResumeSha256: "a".repeat(64),
      createdAt: "2026-08-14T21:00:02.000Z",
    });
    const restored = restoreSessionFromCheckpoint({
      session: freshSession(),
      checkpoint,
      observation: {
        ...observation,
        state: "EDUCATION",
        pageId: "page-2",
        pageFingerprint: "fingerprint-2",
      },
      at: "2026-08-14T21:00:03.000Z",
    });
    expect(restored.status).toBe("RUNNING");
    expect(restored.lastCheckpointSequence).toBe(2);
    expect(restored.completedControlIds).toEqual(["control-1"]);

    const wrong = restoreSessionFromCheckpoint({
      session: freshSession(),
      checkpoint,
      observation: { ...observation, applicationId: "other-app" },
      at: "2026-08-14T21:00:03.000Z",
    });
    expect(wrong.status).toBe("PAUSED_ERROR");
  });

  it("supports an explicit owner pause and fresh-observation resume", () => {
    const started = reduceAutoPilotSession(freshSession(), {
      type: "START",
      observation,
      at: "2026-08-14T21:00:01.000Z",
    });
    const paused = reduceAutoPilotSession(started, {
      type: "PAUSE_OWNER",
      reason: "Owner requested pause",
      at: "2026-08-14T21:00:02.000Z",
    });
    expect(paused.status).toBe("PAUSED_OWNER");
    const resumed = reduceAutoPilotSession(paused, {
      type: "RESUME",
      observation: { ...observation, pageFingerprint: "fingerprint-2" },
      at: "2026-08-14T21:00:03.000Z",
    });
    expect(resumed.status).toBe("RUNNING");
    expect(resumed.pauseReason).toBeNull();
  });
});
