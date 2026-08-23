import { describe, expect, it } from "vitest";
import { parseNativeApplicationAnalyticsSnapshot } from "./native-application-analytics";
import { summarizeApplicationAnalytics } from "@munshi-apply/application-model";

function validSnapshot() {
  return {
    contexts: [
      {
        applicationId: "application-1",
        capturedAt: "2026-08-17T22:30:00.000Z",
        jobSource: "Handshake",
        atsFamily: "WORKDAY",
        resumeId: "resume-1",
      },
    ],
    lifecycleEvents: [
      {
        eventId: "event-1",
        applicationId: "application-1",
        eventType: "AUTOPILOT_COMPLETED",
        occurredAt: "2026-08-17T22:35:00.000Z",
        source: "extension",
        metadata: {},
      },
      {
        eventId: "job-signals-1",
        applicationId: "application-1",
        eventType: "JOB_SIGNALS_ANALYZED",
        occurredAt: "2026-08-17T22:36:00.000Z",
        source: "extension",
        metadata: {
          reportId: "report-1",
          statisticalNote:
            "Observed association only; this does not establish causation.",
        },
      },
    ],
    outcomes: [
      {
        eventId: "outcome-1",
        applicationId: "application-1",
        stage: "INTERVIEW",
        occurredAt: "2026-08-18T15:00:00.000Z",
        source: "owner",
      },
    ],
  };
}

describe("native application analytics parsing", () => {
  it("accepts the complete durable analytics snapshot", () => {
    const snapshot = parseNativeApplicationAnalyticsSnapshot(validSnapshot());
    expect(snapshot.contexts[0]?.jobSource).toBe("Handshake");
    expect(snapshot.lifecycleEvents[0]?.eventType).toBe("AUTOPILOT_COMPLETED");
    expect(snapshot.lifecycleEvents[1]?.eventType).toBe("JOB_SIGNALS_ANALYZED");
    expect(snapshot.outcomes[0]?.stage).toBe("INTERVIEW");

    const summary = summarizeApplicationAnalytics({
      ...snapshot,
      minimumSampleForRates: 1,
    });
    expect(summary.applicationCount).toBe(1);
    expect(summary.interviewCount).toBe(1);
    expect(summary.byAtsFamily[0]?.key).toBe("WORKDAY");
  });

  it("rejects unknown lifecycle and outcome values", () => {
    const snapshot = validSnapshot();
    expect(() =>
      parseNativeApplicationAnalyticsSnapshot({
        ...snapshot,
        lifecycleEvents: [
          { ...snapshot.lifecycleEvents[0], eventType: "AUTO_SUBMITTED" },
        ],
      }),
    ).toThrow(/eventType is invalid/);
    expect(() =>
      parseNativeApplicationAnalyticsSnapshot({
        ...snapshot,
        outcomes: [{ ...snapshot.outcomes[0], stage: "GHOSTED" }],
      }),
    ).toThrow(/stage is invalid/);
  });

  it("rejects timezone-less timestamps and malformed metadata", () => {
    const snapshot = validSnapshot();
    expect(() =>
      parseNativeApplicationAnalyticsSnapshot({
        ...snapshot,
        contexts: [
          { ...snapshot.contexts[0], capturedAt: "2026-08-17T22:30:00" },
        ],
      }),
    ).toThrow(/timezone-aware ISO timestamp/);
    expect(() =>
      parseNativeApplicationAnalyticsSnapshot({
        ...snapshot,
        lifecycleEvents: [
          { ...snapshot.lifecycleEvents[0], metadata: "password=secret" },
        ],
      }),
    ).toThrow(/metadata must be an object/);
  });

  it("keeps missing attribution labels as null instead of inventing categories", () => {
    const snapshot = validSnapshot();
    const parsed = parseNativeApplicationAnalyticsSnapshot({
      ...snapshot,
      contexts: [
        {
          ...snapshot.contexts[0],
          jobSource: null,
          atsFamily: null,
          resumeId: null,
        },
      ],
    });
    expect(parsed.contexts[0]).toMatchObject({
      jobSource: null,
      atsFamily: null,
      resumeId: null,
    });
  });
});
