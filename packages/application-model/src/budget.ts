export type AIUsageRecord = {
  usageId: string;
  provider: string;
  model: string;
  occurredAt: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
};

export type AIBudgetPolicy = {
  monthlyBudgetUsd: number;
  warningBudgetUsd: number;
  hardStop: boolean;
};

export type BudgetDecision = {
  state: "ALLOW" | "WARN" | "BLOCK";
  month: string;
  spentUsd: number;
  plannedCostUsd: number;
  projectedUsd: number;
  remainingUsd: number | null;
  reason: string;
};

function validateNonNegative(value: number, name: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${name} must be a non-negative finite number`);
  }
}

function monthKey(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("Usage timestamp must be a valid ISO date");
  }
  return parsed.toISOString().slice(0, 7);
}

export function validateBudgetPolicy(policy: AIBudgetPolicy): void {
  validateNonNegative(policy.monthlyBudgetUsd, "monthlyBudgetUsd");
  validateNonNegative(policy.warningBudgetUsd, "warningBudgetUsd");
  if (
    policy.monthlyBudgetUsd > 0 &&
    policy.warningBudgetUsd > policy.monthlyBudgetUsd
  ) {
    throw new Error("warningBudgetUsd cannot exceed monthlyBudgetUsd");
  }
}

export function monthlySpend(
  records: readonly AIUsageRecord[],
  at: string,
): number {
  const targetMonth = monthKey(at);
  let total = 0;
  for (const record of records) {
    validateNonNegative(record.inputTokens, "inputTokens");
    validateNonNegative(record.outputTokens, "outputTokens");
    validateNonNegative(record.costUsd, "costUsd");
    if (monthKey(record.occurredAt) === targetMonth) total += record.costUsd;
  }
  return Number(total.toFixed(6));
}

export function evaluateBudgetBeforeRequest(
  policy: AIBudgetPolicy,
  records: readonly AIUsageRecord[],
  plannedCostUsd: number,
  at: string,
): BudgetDecision {
  validateBudgetPolicy(policy);
  validateNonNegative(plannedCostUsd, "plannedCostUsd");
  const month = monthKey(at);
  const spentUsd = monthlySpend(records, at);
  const projectedUsd = Number((spentUsd + plannedCostUsd).toFixed(6));
  const remainingUsd =
    policy.monthlyBudgetUsd > 0
      ? Number(Math.max(0, policy.monthlyBudgetUsd - projectedUsd).toFixed(6))
      : null;

  if (
    policy.monthlyBudgetUsd > 0 &&
    projectedUsd > policy.monthlyBudgetUsd &&
    policy.hardStop
  ) {
    return {
      state: "BLOCK",
      month,
      spentUsd,
      plannedCostUsd,
      projectedUsd,
      remainingUsd,
      reason: "Projected request cost exceeds the configured monthly hard stop",
    };
  }

  if (
    (policy.monthlyBudgetUsd > 0 && projectedUsd > policy.monthlyBudgetUsd) ||
    (policy.warningBudgetUsd > 0 && projectedUsd >= policy.warningBudgetUsd)
  ) {
    return {
      state: "WARN",
      month,
      spentUsd,
      plannedCostUsd,
      projectedUsd,
      remainingUsd,
      reason:
        policy.monthlyBudgetUsd > 0 && projectedUsd > policy.monthlyBudgetUsd
          ? "Projected request cost exceeds the monthly budget, but hard stop is disabled"
          : "Projected request cost reaches the configured warning threshold",
    };
  }

  return {
    state: "ALLOW",
    month,
    spentUsd,
    plannedCostUsd,
    projectedUsd,
    remainingUsd,
    reason: "Projected request cost is within configured budget controls",
  };
}

export function createUsageRecord(input: {
  usageId: string;
  provider: string;
  model: string;
  occurredAt: string;
  inputTokens: number;
  outputTokens: number;
  costUsd: number;
}): AIUsageRecord {
  validateNonNegative(input.inputTokens, "inputTokens");
  validateNonNegative(input.outputTokens, "outputTokens");
  validateNonNegative(input.costUsd, "costUsd");
  monthKey(input.occurredAt);
  if (!input.usageId.trim() || !input.provider.trim() || !input.model.trim()) {
    throw new Error("Usage record identifiers must not be empty");
  }
  return { ...input };
}
