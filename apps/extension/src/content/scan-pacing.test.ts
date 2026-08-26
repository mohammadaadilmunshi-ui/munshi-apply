import { describe, expect, it } from "vitest";
import { automaticScanIntervalMs } from "./scan-pacing";

describe("automatic scan pacing", () => {
  it("keeps fast changing pages responsive when scans are cheap", () => {
    expect(
      automaticScanIntervalMs({ lastScanDurationMs: 40, unchangedScanStreak: 0 }),
    ).toBe(1_200);
  });

  it("backs off in proportion to expensive full-document scans", () => {
    expect(
      automaticScanIntervalMs({ lastScanDurationMs: 750, unchangedScanStreak: 0 }),
    ).toBe(6_000);
  });

  it("backs off repeated scans that produce no new snapshot", () => {
    expect(
      automaticScanIntervalMs({ lastScanDurationMs: 20, unchangedScanStreak: 1 }),
    ).toBe(2_400);
    expect(
      automaticScanIntervalMs({ lastScanDurationMs: 20, unchangedScanStreak: 3 }),
    ).toBe(9_600);
  });

  it("caps automatic pacing while explicit scan requests remain separate", () => {
    expect(
      automaticScanIntervalMs({ lastScanDurationMs: 9_000, unchangedScanStreak: 20 }),
    ).toBe(10_000);
  });
});
