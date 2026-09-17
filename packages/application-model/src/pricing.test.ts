import { describe, expect, it } from "vitest";
import {
  calculateUsageCost,
  estimateRequestCost,
  type ModelPricing,
} from "./pricing";

const pricing: ModelPricing = {
  provider: "openai",
  model: "gpt-test",
  inputUsdPerMillionTokens: 2,
  outputUsdPerMillionTokens: 8,
  source: "owner-configured-test-rate",
  effectiveAt: "2026-08-14T18:00:00.000Z",
};

describe("explicit model pricing", () => {
  it("calculates actual usage cost from configured rates", () => {
    expect(
      calculateUsageCost(pricing, {
        inputTokens: 500_000,
        outputTokens: 250_000,
      }),
    ).toBe(3);
  });

  it("estimates worst-case request cost from input estimate and output cap", () => {
    expect(estimateRequestCost(pricing, 100_000, 100_000)).toBe(1);
  });

  it("rejects negative or malformed pricing instead of assuming a rate", () => {
    expect(() =>
      calculateUsageCost(
        { ...pricing, inputUsdPerMillionTokens: -1 },
        { inputTokens: 1, outputTokens: 1 },
      ),
    ).toThrow("inputUsdPerMillionTokens");
  });
});
