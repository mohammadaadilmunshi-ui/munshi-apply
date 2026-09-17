const MIN_AUTOMATIC_SCAN_INTERVAL_MS = 1_200;
const MAX_AUTOMATIC_SCAN_INTERVAL_MS = 10_000;
const SCAN_COST_MULTIPLIER = 8;
const MAX_STABILITY_BACKOFF_STEPS = 3;

export function automaticScanIntervalMs(input: {
  lastScanDurationMs: number;
  unchangedScanStreak: number;
}): number {
  const duration = Math.max(0, input.lastScanDurationMs);
  const unchanged = Math.max(0, Math.floor(input.unchangedScanStreak));
  const durationInterval = Math.ceil(duration * SCAN_COST_MULTIPLIER);
  const stabilitySteps = Math.min(unchanged, MAX_STABILITY_BACKOFF_STEPS);
  const stabilityInterval =
    MIN_AUTOMATIC_SCAN_INTERVAL_MS * Math.pow(2, stabilitySteps);

  return Math.min(
    MAX_AUTOMATIC_SCAN_INTERVAL_MS,
    Math.max(
      MIN_AUTOMATIC_SCAN_INTERVAL_MS,
      durationInterval,
      stabilityInterval,
    ),
  );
}
