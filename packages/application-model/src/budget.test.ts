import { describe, expect, it } from "vitest";
import {
  createUsageRecord,
  evaluateBudgetBeforeRequest,
  monthlySpend,
} from "./budget";

const records = [
  createUsageRecord({
    usageId: "u-1",
    provider: "openai",
    model: "gpt-test",
    occurredAt: "2026-08-01T12:00:00.000Z",
    inputTokens: 100,
    outputTokens: 50,
    costUsd: 3,
  }),
  createUsageRecord({
    usageId: "u-2",
    provider: "openai",
    model: "gpt-test",
    occurredAt: "2026-07-31T23:00:00.000Z",
    inputTokens: 100,
    outputTokens: 50,
    costUsd: 99,
  }),
];

describe("monthlySpend", () => {
  it("counts only records in the evaluated UTC month", () => {
    expect(monthlySpend(records, "2026-08-14T18:00:00.000Z")).toBe(3);
  });
});

describe("evaluateBudgetBeforeRequest", () => {
  it("allows a request below warning and monthly thresholds", () => {
    expect(
      evaluateBudgetBeforeRequest(
        { monthlyBudgetUsd: 10, warningBudgetUsd: 8, hardStop: true },
        records,
        2,
        "2026-08-14T18:00:00.000Z",
      ),
    ).toMatchObject({
      state: "ALLOW",
      spentUsd: 3,
      projectedUsd: 5,
      remainingUsd: 5,
    });
  });

  it("warns before a request reaches the warning threshold", () => {
    const decision = evaluateBudgetBeforeRequest(
      { monthlyBudgetUsd: 10, warningBudgetUsd: 8, hardStop: true },
      records,
      5,
      "2026-08-14T18:00:00.000Z",
    );
    expect(decision.state).toBe("WARN");
    expect(decision.projectedUsd).toBe(8);
  });

  it("blocks before spending beyond a monthly hard stop", () => {
    const decision = evaluateBudgetBeforeRequest(
      { monthlyBudgetUsd: 10, warningBudgetUsd: 8, hardStop: true },
      records,
      8,
      "2026-08-14T18:00:00.000Z",
    );
    expect(decision.state).toBe("BLOCK");
    expect(decision.projectedUsd).toBe(11);
  });

  it("warns rather than blocks above budget when hard stop is disabled", () => {
    const decision = evaluateBudgetBeforeRequest(
      { monthlyBudgetUsd: 10, warningBudgetUsd: 8, hardStop: false },
      records,
      8,
      "2026-08-14T18:00:00.000Z",
    );
    expect(decision.state).toBe("WARN");
  });

  it("supports a zero monthly budget as an unlimited budget with no implicit spend", () => {
    const decision = evaluateBudgetBeforeRequest(
      { monthlyBudgetUsd: 0, warningBudgetUsd: 0, hardStop: true },
      [],
      100,
      "2026-08-14T18:00:00.000Z",
    );
    expect(decision).toMatchObject({ state: "ALLOW", remainingUsd: null });
  });
});
