import type { SemanticType } from "@munshi-apply/contracts";

export type ProgressiveMemoryKind =
  | "SITE"
  | "QUESTION"
  | "FAILURE"
  | "SUCCESS"
  | "USER_CORRECTION"
  | "GLOBAL_PATTERN";

export type ProgressiveMemoryState = "ACTIVE" | "SUPPRESSED" | "ROLLED_BACK";

export type ProgressiveMemory = {
  memoryId: string;
  kind: ProgressiveMemoryKind;
  semanticType: SemanticType | null;
  siteOrigin: string | null;
  componentFingerprint: string | null;
  questionFingerprint: string | null;
  interpretationKey: string | null;
  strategyKey: string | null;
  canonicalOptionKey: string | null;
  confidence: number;
  verifiedSuccesses: number;
  verifiedFailures: number;
  ownerCorrections: number;
  createdAt: string;
  lastObservedAt: string;
  expiresAt: string | null;
  version: number;
  state: ProgressiveMemoryState;
};

export type ProgressiveMemoryObservation = {
  success: boolean;
  verified: boolean;
  ownerCorrected: boolean;
  observedAt: string;
};

export type ProgressiveMemoryQuery = {
  semanticType: SemanticType | null;
  siteOrigin: string | null;
  componentFingerprint: string | null;
  questionFingerprint: string | null;
  now: string;
  sensitive: boolean;
};

export type RankedProgressiveMemory = {
  memory: ProgressiveMemory;
  score: number;
  reasons: string[];
};

export type ProgressiveMemoryConflictResolution = {
  winner: ProgressiveMemory | null;
  reviewRequired: boolean;
  reason: string;
};

const kindPriorities: Record<ProgressiveMemoryKind, number> = {
  USER_CORRECTION: 1,
  SITE: 0.9,
  QUESTION: 0.86,
  SUCCESS: 0.76,
  FAILURE: 0.72,
  GLOBAL_PATTERN: 0.58,
};

function clamp(value: number, minimum = 0, maximum = 1): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizedOrigin(value: string | null): string | null {
  if (!value) return null;
  try {
    return new URL(value).origin.toLowerCase();
  } catch {
    return value.trim().toLowerCase() || null;
  }
}

function validIsoDate(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

export function validateProgressiveMemory(memory: ProgressiveMemory): void {
  if (!memory.memoryId.trim()) throw new Error("Memory id is required");
  if (!Number.isInteger(memory.version) || memory.version < 1) {
    throw new Error("Memory version must be a positive integer");
  }
  if (
    !Number.isFinite(memory.confidence) ||
    memory.confidence < 0 ||
    memory.confidence > 1
  ) {
    throw new Error("Memory confidence must be between 0 and 1");
  }
  for (const count of [
    memory.verifiedSuccesses,
    memory.verifiedFailures,
    memory.ownerCorrections,
  ]) {
    if (!Number.isSafeInteger(count) || count < 0) {
      throw new Error("Memory counters must be non-negative integers");
    }
  }
  if (!validIsoDate(memory.createdAt) || !validIsoDate(memory.lastObservedAt)) {
    throw new Error("Memory timestamps must be valid dates");
  }
  if (memory.expiresAt && !validIsoDate(memory.expiresAt)) {
    throw new Error("Memory expiry must be a valid date");
  }
  if (
    memory.kind === "GLOBAL_PATTERN" &&
    (memory.siteOrigin !== null || memory.questionFingerprint !== null)
  ) {
    throw new Error("Global memory cannot be site/question bound");
  }
  if (memory.kind === "SITE" && !memory.siteOrigin) {
    throw new Error("Site memory requires a site origin");
  }
  if (memory.kind === "QUESTION" && !memory.questionFingerprint) {
    throw new Error("Question memory requires a question fingerprint");
  }
  if (
    memory.kind === "USER_CORRECTION" &&
    !memory.questionFingerprint &&
    !memory.interpretationKey
  ) {
    throw new Error(
      "User correction memory requires a question fingerprint or interpretation key",
    );
  }
}

/**
 * Confidence adapts only from verified outcomes. Owner corrections lower the
 * confidence of the previous interpretation aggressively so the same failed
 * interpretation is not repeated blindly.
 */
export function applyProgressiveMemoryObservation(
  memory: ProgressiveMemory,
  observation: ProgressiveMemoryObservation,
): ProgressiveMemory {
  validateProgressiveMemory(memory);
  if (!validIsoDate(observation.observedAt)) {
    throw new Error("Observation time must be a valid date");
  }
  if (!observation.verified) {
    return { ...memory, lastObservedAt: observation.observedAt };
  }

  const successDelta = observation.success ? 1 : 0;
  const failureDelta = observation.success ? 0 : 1;
  const correctionDelta = observation.ownerCorrected ? 1 : 0;
  const verifiedSuccesses = memory.verifiedSuccesses + successDelta;
  const verifiedFailures = memory.verifiedFailures + failureDelta;
  const ownerCorrections = memory.ownerCorrections + correctionDelta;

  const evidenceTotal = verifiedSuccesses + verifiedFailures;
  const empirical = evidenceTotal === 0 ? 0.5 : verifiedSuccesses / evidenceTotal;
  const evidenceWeight = Math.min(0.82, evidenceTotal / (evidenceTotal + 4));
  const priorWeight = 1 - evidenceWeight;
  let confidence = priorWeight * memory.confidence + evidenceWeight * empirical;

  if (observation.ownerCorrected) {
    confidence *= 0.45;
  } else if (observation.success) {
    confidence += 0.035;
  } else {
    confidence -= 0.08;
  }

  return {
    ...memory,
    confidence: Number(clamp(confidence).toFixed(6)),
    verifiedSuccesses,
    verifiedFailures,
    ownerCorrections,
    lastObservedAt: observation.observedAt,
    version: memory.version + 1,
  };
}

export function progressiveMemoryDecay(
  memory: ProgressiveMemory,
  now: string,
  halfLifeDays = 120,
): number {
  validateProgressiveMemory(memory);
  if (!validIsoDate(now)) throw new Error("Current time must be a valid date");
  if (!Number.isFinite(halfLifeDays) || halfLifeDays <= 0) {
    throw new Error("Memory half-life must be positive");
  }
  const elapsedDays = Math.max(
    0,
    (Date.parse(now) - Date.parse(memory.lastObservedAt)) / 86_400_000,
  );
  return Number(Math.pow(0.5, elapsedDays / halfLifeDays).toFixed(6));
}

function memoryExpired(memory: ProgressiveMemory, now: string): boolean {
  const expiresAt = memory.expiresAt;
  return expiresAt !== null && Date.parse(expiresAt) <= Date.parse(now);
}

function compatibleWithQuery(
  memory: ProgressiveMemory,
  query: ProgressiveMemoryQuery,
): { compatible: boolean; score: number; reasons: string[] } {
  if (memory.state !== "ACTIVE" || memoryExpired(memory, query.now)) {
    return { compatible: false, score: 0, reasons: [] };
  }

  const reasons: string[] = [];
  let score = kindPriorities[memory.kind] * memory.confidence;
  const memoryOrigin = normalizedOrigin(memory.siteOrigin);
  const queryOrigin = normalizedOrigin(query.siteOrigin);

  if (memory.semanticType && query.semanticType) {
    if (memory.semanticType !== query.semanticType) {
      return { compatible: false, score: 0, reasons: [] };
    }
    score += 0.12;
    reasons.push("semantic type match");
  }

  if (memoryOrigin) {
    if (!queryOrigin || memoryOrigin !== queryOrigin) {
      return { compatible: false, score: 0, reasons: [] };
    }
    score += 0.18;
    reasons.push("site match");
  }

  if (memory.componentFingerprint) {
    if (
      !query.componentFingerprint ||
      memory.componentFingerprint !== query.componentFingerprint
    ) {
      if (memory.kind !== "GLOBAL_PATTERN") {
        return { compatible: false, score: 0, reasons: [] };
      }
    } else {
      score += 0.18;
      reasons.push("component match");
    }
  }

  if (memory.questionFingerprint) {
    if (
      !query.questionFingerprint ||
      memory.questionFingerprint !== query.questionFingerprint
    ) {
      return { compatible: false, score: 0, reasons: [] };
    }
    score += 0.24;
    reasons.push("question match");
  }

  if (query.sensitive && memory.kind === "GLOBAL_PATTERN") {
    return { compatible: false, score: 0, reasons: [] };
  }

  if (memory.kind === "USER_CORRECTION") {
    score += 0.2;
    reasons.push("owner correction");
  }

  score *= progressiveMemoryDecay(memory, query.now);
  return { compatible: true, score: clamp(score, 0, 2), reasons };
}

export function rankProgressiveMemory(
  memories: readonly ProgressiveMemory[],
  query: ProgressiveMemoryQuery,
  limit = 8,
): RankedProgressiveMemory[] {
  if (!Number.isSafeInteger(limit) || limit < 1) {
    throw new Error("Memory result limit must be a positive integer");
  }
  if (!validIsoDate(query.now)) {
    throw new Error("Current time must be a valid date");
  }

  return memories
    .map((memory) => {
      validateProgressiveMemory(memory);
      const match = compatibleWithQuery(memory, query);
      return {
        memory,
        score: Number(match.score.toFixed(6)),
        reasons: match.reasons,
        compatible: match.compatible,
      };
    })
    .filter((candidate) => candidate.compatible)
    .sort(
      (left, right) =>
        right.score - left.score ||
        right.memory.lastObservedAt.localeCompare(left.memory.lastObservedAt) ||
        left.memory.memoryId.localeCompare(right.memory.memoryId),
    )
    .slice(0, limit)
    .map(({ memory, score, reasons }) => ({ memory, score, reasons }));
}

/**
 * Conflicting memories never silently overwrite each other. The best-supported
 * active interpretation is returned only when its margin is large enough;
 * otherwise the caller must review the ambiguity.
 */
export function resolveProgressiveMemoryConflict(
  ranked: readonly RankedProgressiveMemory[],
  minimumMargin = 0.15,
): ProgressiveMemoryConflictResolution {
  if (!Number.isFinite(minimumMargin) || minimumMargin < 0) {
    throw new Error("Memory conflict margin must be non-negative");
  }
  const first = ranked[0];
  if (!first) {
    return {
      winner: null,
      reviewRequired: false,
      reason: "No compatible memory is available",
    };
  }
  const second = ranked.find(
    (candidate) =>
      candidate.memory.interpretationKey !== first.memory.interpretationKey ||
      candidate.memory.strategyKey !== first.memory.strategyKey ||
      candidate.memory.canonicalOptionKey !== first.memory.canonicalOptionKey,
  );
  if (!second || first.score - second.score >= minimumMargin) {
    return {
      winner: first.memory,
      reviewRequired: false,
      reason: "One compatible memory is sufficiently better supported",
    };
  }
  return {
    winner: null,
    reviewRequired: true,
    reason: "Conflicting memories are too close to choose safely",
  };
}
