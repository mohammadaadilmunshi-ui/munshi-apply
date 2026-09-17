import { describe, expect, it } from "vitest";
import { parseAIControlStatus, parseAISettings } from "./native";

const settings = {
  provider: "openai",
  enabled: true,
  model: "gpt-5.6-luna",
  monthlyBudgetUsd: 5,
  warningBudgetUsd: 4,
  hardStop: true,
  allowApplicationDrafts: true,
  allowProfileEvidence: true,
  allowResumeEvidence: false,
  keyConfigured: true,
  keySource: "keychain",
};

describe("native AI control contracts", () => {
  it("parses owner AI permissions without exposing a credential field", () => {
    const parsed = parseAISettings(settings);
    expect(parsed.allowApplicationDrafts).toBe(true);
    expect(parsed.allowResumeEvidence).toBe(false);
    expect("apiKey" in parsed).toBe(false);
  });

  it("requires permanent native guardrails to remain locked", () => {
    expect(() =>
      parseAIControlStatus({
        settings,
        usage: {
          month: "2026-08",
          spentUsd: 0,
          reservedUsd: 0,
          projectedUsd: 0,
          remainingUsd: 5,
          requestCount: 0,
          inputTokens: 0,
          outputTokens: 0,
          estimatedCostUsd: 0,
        },
        pricing: null,
        guardrails: {
          safeDraftSemanticTypes: ["WHY_ROLE"],
          consequentialQuestionsManual: false,
          protectedEvidenceExcluded: true,
          ownerReviewRequired: true,
          finalSubmissionManual: true,
        },
      }),
    ).toThrow(/consequentialQuestionsManual/);
  });

  it("parses usage and verified pricing status", () => {
    const parsed = parseAIControlStatus({
      settings,
      usage: {
        month: "2026-08",
        spentUsd: 0.12,
        reservedUsd: 0.03,
        projectedUsd: 0.15,
        remainingUsd: 4.85,
        requestCount: 2,
        inputTokens: 1000,
        outputTokens: 200,
        estimatedCostUsd: 0,
      },
      pricing: {
        provider: "openai",
        model: "gpt-5.6-luna",
        inputUsdPerMillionTokens: 1,
        outputUsdPerMillionTokens: 6,
        verifiedAt: "2026-08-14T00:00:00+00:00",
        source: "OpenAI API pricing",
        ageDays: 0,
        stale: false,
      },
      guardrails: {
        safeDraftSemanticTypes: ["WHY_ROLE"],
        consequentialQuestionsManual: true,
        protectedEvidenceExcluded: true,
        ownerReviewRequired: true,
        finalSubmissionManual: true,
      },
    });
    expect(parsed.usage.projectedUsd).toBe(0.15);
    expect(parsed.pricing?.model).toBe("gpt-5.6-luna");
  });
});
