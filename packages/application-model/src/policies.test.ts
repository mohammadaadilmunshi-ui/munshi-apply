import type { Question } from "@munshi-apply/contracts";
import { describe, expect, it } from "vitest";
import type { AnswerResolution } from "./resolver";
import {
  detectTrustedContradiction,
  evaluateKnockoutQuestion,
  evaluateSalaryRanges,
  summarizePreflightGate,
} from "./policies";

const question: Question = {
  questionId: "q-1",
  controlId: "c-1",
  rawText: "Do you currently require sponsorship?",
  semanticType: "SPONSORSHIP_CURRENT",
  confidence: 0.9,
  sensitive: true,
  requiresReview: true,
};

const resolution: AnswerResolution = {
  state: "REVIEW",
  value: "No",
  sourceFactId: "fact-1",
  sourceKey: "current_sponsorship",
  trustLevel: "USER_CONFIRMED",
  sensitive: true,
  protected: true,
  confidence: 0.9,
  reasons: ["Source fact is protected"],
};

describe("detectTrustedContradiction", () => {
  it("blocks conflicting authoritative protected facts", () => {
    const result = detectTrustedContradiction("current_sponsorship", [
      {
        sourceId: "profile",
        value: "No",
        trustLevel: "USER_CONFIRMED",
        protected: true,
      },
      {
        sourceId: "document",
        value: "Yes",
        trustLevel: "DOCUMENT_CONFIRMED",
        protected: true,
      },
    ]);

    expect(result.state).toBe("BLOCKED");
    expect(result.distinctValues).toEqual(["no", "yes"]);
  });

  it("ignores generated values when looking for authoritative contradictions", () => {
    const result = detectTrustedContradiction("employer", [
      {
        sourceId: "verified",
        value: "Example Co",
        trustLevel: "VERIFIED",
        protected: false,
      },
      {
        sourceId: "draft",
        value: "Different Co",
        trustLevel: "GENERATED",
        protected: false,
      },
    ]);

    expect(result.state).toBe("CLEAR");
  });
});

describe("evaluateKnockoutQuestion", () => {
  it("does not invent a knockout rule when none was supplied", () => {
    const result = evaluateKnockoutQuestion(question, resolution, null);
    expect(result.state).toBe("REVIEW");
    expect(result.matchedRule).toBe(false);
  });

  it("blocks only when an explicit rule matches the resolved answer", () => {
    const result = evaluateKnockoutQuestion(question, resolution, {
      semanticType: "SPONSORSHIP_CURRENT",
      disqualifyingValues: ["No"],
      source: "job-posting-rule",
    });

    expect(result.state).toBe("BLOCKED");
    expect(result.disqualifying).toBe(true);
  });

  it("blocks unresolved knockout-sensitive answers before action", () => {
    const result = evaluateKnockoutQuestion(
      question,
      { ...resolution, state: "UNRESOLVED", value: null },
      null,
    );
    expect(result.state).toBe("BLOCKED");
  });
});

describe("evaluateSalaryRanges", () => {
  it("reports overlap but still requires owner review", () => {
    const result = evaluateSalaryRanges(
      { minimum: 80000, maximum: 90000, currency: "USD", period: "YEAR" },
      { minimum: 85000, maximum: 100000, currency: "USD", period: "YEAR" },
    );

    expect(result).toMatchObject({ state: "REVIEW", overlaps: true });
  });

  it("does not auto-reject when ranges do not overlap", () => {
    const result = evaluateSalaryRanges(
      { minimum: 100000, maximum: 110000, currency: "USD", period: "YEAR" },
      { minimum: 70000, maximum: 90000, currency: "USD", period: "YEAR" },
    );

    expect(result).toMatchObject({ state: "REVIEW", overlaps: false });
    expect(result.reason).toContain("do not reject");
  });
});

describe("summarizePreflightGate", () => {
  it("permits action only when every gate item is ready", () => {
    expect(
      summarizePreflightGate([
        { id: "a", state: "READY" },
        { id: "b", state: "READY" },
      ]),
    ).toMatchObject({ state: "READY", canAct: true });

    expect(
      summarizePreflightGate([
        { id: "a", state: "READY" },
        { id: "b", state: "REVIEW" },
      ]),
    ).toMatchObject({ state: "REVIEW", canAct: false });

    expect(
      summarizePreflightGate([{ id: "a", state: "UNRESOLVED" }]),
    ).toMatchObject({ state: "BLOCKED", canAct: false });
  });
});
