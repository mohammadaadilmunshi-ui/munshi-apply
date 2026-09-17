import { describe, expect, it } from "vitest";
import {
  applyProgressiveMemoryObservation,
  progressiveMemoryDecay,
  rankProgressiveMemory,
  resolveProgressiveMemoryConflict,
  type ProgressiveMemory,
} from "./progressive-memory";

const now = "2026-08-17T18:00:00.000Z";

function memory(overrides: Partial<ProgressiveMemory> = {}): ProgressiveMemory {
  return {
    memoryId: "memory-1",
    kind: "SITE",
    semanticType: "COUNTRY",
    siteOrigin: "https://jobs.example.test",
    componentFingerprint: "cfp-country",
    questionFingerprint: "q-country",
    interpretationKey: "location.country",
    strategyKey: "ARIA_COMBOBOX",
    canonicalOptionKey: "country:US",
    confidence: 0.72,
    verifiedSuccesses: 3,
    verifiedFailures: 1,
    ownerCorrections: 0,
    createdAt: "2026-08-10T18:00:00.000Z",
    lastObservedAt: "2026-08-17T17:00:00.000Z",
    expiresAt: null,
    version: 1,
    state: "ACTIVE",
    ...overrides,
  };
}

describe("progressive memory", () => {
  it("raises confidence after a verified successful reuse", () => {
    const before = memory();
    const after = applyProgressiveMemoryObservation(before, {
      success: true,
      verified: true,
      ownerCorrected: false,
      observedAt: now,
    });

    expect(after.confidence).toBeGreaterThan(before.confidence);
    expect(after.verifiedSuccesses).toBe(4);
    expect(after.version).toBe(2);
  });

  it("deprioritizes an interpretation after an owner correction", () => {
    const before = memory();
    const after = applyProgressiveMemoryObservation(before, {
      success: false,
      verified: true,
      ownerCorrected: true,
      observedAt: now,
    });

    expect(after.confidence).toBeLessThan(before.confidence / 2);
    expect(after.ownerCorrections).toBe(1);
  });

  it("does not change evidence counters for an unverified observation", () => {
    const before = memory();
    const after = applyProgressiveMemoryObservation(before, {
      success: true,
      verified: false,
      ownerCorrected: false,
      observedAt: now,
    });

    expect(after.confidence).toBe(before.confidence);
    expect(after.verifiedSuccesses).toBe(before.verifiedSuccesses);
    expect(after.version).toBe(before.version);
  });

  it("ages old memory instead of keeping it permanently authoritative", () => {
    const old = memory({ lastObservedAt: "2026-04-19T18:00:00.000Z" });
    expect(progressiveMemoryDecay(old, now, 120)).toBeCloseTo(0.5, 2);
  });

  it("ranks exact memory above a global pattern", () => {
    const exact = memory({ memoryId: "exact" });
    const global = memory({
      memoryId: "global",
      kind: "GLOBAL_PATTERN",
      siteOrigin: null,
      questionFingerprint: null,
      componentFingerprint: null,
      confidence: 0.95,
    });

    const ranked = rankProgressiveMemory([global, exact], {
      semanticType: "COUNTRY",
      siteOrigin: "https://jobs.example.test/apply",
      componentFingerprint: "cfp-country",
      questionFingerprint: "q-country",
      now,
      sensitive: false,
    });

    expect(ranked[0]?.memory.memoryId).toBe("exact");
  });

  it("does not apply global pattern memory to sensitive questions", () => {
    const global = memory({
      memoryId: "global",
      kind: "GLOBAL_PATTERN",
      siteOrigin: null,
      questionFingerprint: null,
      componentFingerprint: null,
    });

    const ranked = rankProgressiveMemory([global], {
      semanticType: "COUNTRY",
      siteOrigin: "https://jobs.example.test",
      componentFingerprint: "cfp-country",
      questionFingerprint: "q-country",
      now,
      sensitive: true,
    });

    expect(ranked).toEqual([]);
  });

  it("requires review when conflicting interpretations are too close", () => {
    const ranked = rankProgressiveMemory(
      [
        memory({ memoryId: "first", interpretationKey: "country.home" }),
        memory({
          memoryId: "second",
          interpretationKey: "country.citizenship",
          confidence: 0.71,
        }),
      ],
      {
        semanticType: "COUNTRY",
        siteOrigin: "https://jobs.example.test",
        componentFingerprint: "cfp-country",
        questionFingerprint: "q-country",
        now,
        sensitive: false,
      },
    );

    const resolution = resolveProgressiveMemoryConflict(ranked, 0.15);
    expect(resolution.reviewRequired).toBe(true);
    expect(resolution.winner).toBeNull();
  });

  it("lets an owner correction win when it has a clear support margin", () => {
    const ranked = rankProgressiveMemory(
      [
        memory({
          memoryId: "owner",
          kind: "USER_CORRECTION",
          confidence: 0.95,
          interpretationKey: "country.citizenship",
        }),
        memory({
          memoryId: "old",
          confidence: 0.3,
          interpretationKey: "country.home",
        }),
      ],
      {
        semanticType: "COUNTRY",
        siteOrigin: "https://jobs.example.test",
        componentFingerprint: "cfp-country",
        questionFingerprint: "q-country",
        now,
        sensitive: false,
      },
    );

    const resolution = resolveProgressiveMemoryConflict(ranked, 0.15);
    expect(resolution.reviewRequired).toBe(false);
    expect(resolution.winner?.memoryId).toBe("owner");
  });
});
