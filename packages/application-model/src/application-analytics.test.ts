import { describe, expect, it } from "vitest";
import type { ApplicationOutcomeEvent } from "./analytics";
import {
  summarizeApplicationAnalytics,
  type ApplicationAttributionContext,
  type ApplicationLifecycleEvent,
} from "./application-analytics";

function outcome(
  applicationId: string,
  stage: ApplicationOutcomeEvent["stage"],
): ApplicationOutcomeEvent {
  return {
    eventId: `${applicationId}-${stage}`,
    applicationId,
    stage,
    occurredAt: "2026-08-17T22:30:00.000Z",
    source: "owner",
  };
}

function context(
  applicationId: string,
  jobSource: string,
  atsFamily: string,
  resumeId: string,
): ApplicationAttributionContext {
  return {
    applicationId,
    capturedAt: "2026-08-17T22:00:00.000Z",
    jobSource,
    atsFamily,
    resumeId,
  };
}

function event(
  applicationId: string,
  eventType: ApplicationLifecycleEvent["eventType"],
): ApplicationLifecycleEvent {
  return {
    eventId: `${applicationId}-${eventType}`,
    applicationId,
    eventType,
    occurredAt: "2026-08-17T22:15:00.000Z",
    source: "extension",
  };
}

describe("application analytics", () => {
  it("deduplicates applications while counting every reached funnel stage", () => {
    const summary = summarizeApplicationAnalytics({
      contexts: [context("app-1", "Handshake", "WORKDAY", "resume-a")],
      lifecycleEvents: [
        event("app-1", "PREPARED"),
        event("app-1", "AUTOPILOT_COMPLETED"),
      ],
      outcomes: [
        outcome("app-1", "APPLIED"),
        outcome("app-1", "INTERVIEW"),
        outcome("app-1", "REJECTED"),
      ],
    });
    expect(summary.applicationCount).toBe(1);
    expect(summary.preparedCount).toBe(1);
    expect(summary.appliedCount).toBe(1);
    expect(summary.responseCount).toBe(1);
    expect(summary.interviewCount).toBe(1);
    expect(summary.rejectedCount).toBe(1);
    expect(summary.autopilotCompletedCount).toBe(1);
  });

  it("uses the latest attribution context for each application", () => {
    const summary = summarizeApplicationAnalytics({
      contexts: [
        context("app-1", "Unknown", "GENERIC", "resume-old"),
        {
          ...context("app-1", "LinkedIn", "GREENHOUSE", "resume-new"),
          capturedAt: "2026-08-17T22:10:00.000Z",
        },
      ],
      lifecycleEvents: [],
      outcomes: [outcome("app-1", "APPLIED")],
      minimumSampleForRates: 1,
    });
    expect(summary.byJobSource[0]?.key).toBe("LinkedIn");
    expect(summary.byAtsFamily[0]?.key).toBe("GREENHOUSE");
    expect(summary.byResume[0]?.key).toBe("resume-new");
  });

  it("withholds rates below the sample gate while preserving counts", () => {
    const summary = summarizeApplicationAnalytics({
      contexts: [
        context("app-1", "Handshake", "WORKDAY", "resume-a"),
        context("app-2", "Handshake", "WORKDAY", "resume-a"),
      ],
      lifecycleEvents: [],
      outcomes: [
        outcome("app-1", "APPLIED"),
        outcome("app-1", "INTERVIEW"),
        outcome("app-2", "APPLIED"),
      ],
      minimumSampleForRates: 5,
    });
    const bucket = summary.byJobSource[0]!;
    expect(bucket.sampleCount).toBe(2);
    expect(bucket.interviewCount).toBe(1);
    expect(bucket.interviewRate).toBeNull();
    expect(bucket.rateReason).toMatch(/at least 5 applications/i);
  });

  it("shows descriptive rates once the minimum sample gate is met", () => {
    const contexts = Array.from({ length: 5 }, (_, index) =>
      context(`app-${index}`, "Handshake", "WORKDAY", "resume-a"),
    );
    const outcomes = contexts.flatMap((item, index) => [
      outcome(item.applicationId, "APPLIED"),
      ...(index < 2 ? [outcome(item.applicationId, "INTERVIEW")] : []),
    ]);
    const summary = summarizeApplicationAnalytics({
      contexts,
      lifecycleEvents: [],
      outcomes,
      minimumSampleForRates: 5,
    });
    const bucket = summary.byJobSource[0]!;
    expect(bucket.interviewRate).toBe(0.4);
    expect(bucket.rateReason).toMatch(/do not establish causality/i);
  });

  it("counts a recruiter response without inventing an interview outcome", () => {
    const summary = summarizeApplicationAnalytics({
      contexts: [context("app-1", "Referral", "LEVER", "resume-a")],
      lifecycleEvents: [event("app-1", "RECRUITER_RESPONSE")],
      outcomes: [outcome("app-1", "APPLIED")],
      minimumSampleForRates: 1,
    });
    expect(summary.responseCount).toBe(1);
    expect(summary.interviewCount).toBe(0);
    expect(summary.byJobSource[0]?.responseRate).toBe(1);
    expect(summary.byJobSource[0]?.interviewRate).toBe(0);
  });

  it("groups missing attribution under UNKNOWN instead of dropping applications", () => {
    const summary = summarizeApplicationAnalytics({
      contexts: [],
      lifecycleEvents: [event("app-1", "DETECTED")],
      outcomes: [],
      minimumSampleForRates: 1,
    });
    expect(summary.applicationCount).toBe(1);
    expect(summary.byJobSource[0]?.key).toBe("UNKNOWN");
    expect(summary.byAtsFamily[0]?.key).toBe("UNKNOWN");
    expect(summary.byResume[0]?.key).toBe("UNKNOWN");
  });

  it("rejects an invalid statistical sample gate", () => {
    expect(() =>
      summarizeApplicationAnalytics({
        contexts: [],
        lifecycleEvents: [],
        outcomes: [],
        minimumSampleForRates: 0,
      }),
    ).toThrow(/positive integer/);
  });
});
