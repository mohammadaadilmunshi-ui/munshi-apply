export type ModelPricing = {
  provider: string;
  model: string;
  inputUsdPerMillionTokens: number;
  outputUsdPerMillionTokens: number;
  source: string;
  effectiveAt: string;
};

export type UsageCostInput = {
  inputTokens: number;
  outputTokens: number;
};

function validateRate(value: number, name: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative finite number`);
  }
}

function validateTokens(value: number, name: string): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${name} must be a non-negative integer`);
  }
}

export function validateModelPricing(pricing: ModelPricing): void {
  if (!pricing.provider.trim() || !pricing.model.trim()) {
    throw new Error("Provider and model pricing identifiers are required");
  }
  if (!pricing.source.trim()) {
    throw new Error("Pricing source is required");
  }
  if (Number.isNaN(new Date(pricing.effectiveAt).getTime())) {
    throw new Error("Pricing effectiveAt must be a valid date");
  }
  validateRate(pricing.inputUsdPerMillionTokens, "inputUsdPerMillionTokens");
  validateRate(pricing.outputUsdPerMillionTokens, "outputUsdPerMillionTokens");
}

export function calculateUsageCost(
  pricing: ModelPricing,
  usage: UsageCostInput,
): number {
  validateModelPricing(pricing);
  validateTokens(usage.inputTokens, "inputTokens");
  validateTokens(usage.outputTokens, "outputTokens");
  const inputCost =
    (usage.inputTokens / 1_000_000) * pricing.inputUsdPerMillionTokens;
  const outputCost =
    (usage.outputTokens / 1_000_000) * pricing.outputUsdPerMillionTokens;
  return Number((inputCost + outputCost).toFixed(8));
}

export function estimateRequestCost(
  pricing: ModelPricing,
  estimatedInputTokens: number,
  maximumOutputTokens: number,
): number {
  validateTokens(estimatedInputTokens, "estimatedInputTokens");
  validateTokens(maximumOutputTokens, "maximumOutputTokens");
  return calculateUsageCost(pricing, {
    inputTokens: estimatedInputTokens,
    outputTokens: maximumOutputTokens,
  });
}
