import {
  APPLICATION_TRUTH_CACHE_VERSION,
  HunterApplicationTruthProjectionSchema,
  HunterTruthCacheSchema,
  classifyHunterTruthUpdate,
  resolveCanonicalHunterFact,
  type HunterApplicationTruthProjection,
  type HunterTruthCache,
  type HunterTruthUpdateDisposition,
} from "@munshi-apply/contracts/career-os-phase8";
import { ProfileFactSchema, type ProfileFact } from "@munshi-apply/contracts";

const storageKey = "munshi.apply.hunter-candidate-truth.v1";

export type HunterTruthCacheStore = {
  load: () => Promise<unknown | null>;
  save: (cache: HunterTruthCache) => Promise<void>;
};

const defaultStore: HunterTruthCacheStore = {
  async load() {
    const result = await chrome.storage.local.get(storageKey);
    return result[storageKey] ?? null;
  },
  async save(cache) {
    await chrome.storage.local.set({ [storageKey]: cache });
  },
};

function canonicalValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalValue(item)]),
    );
  }
  return value;
}

function projectionDigestPayload(
  projection: HunterApplicationTruthProjection,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(projection).filter(
      ([key]) => key !== "generated_at" && key !== "projection_digest",
    ),
  );
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyHunterTruthProjectionIntegrity(
  value: unknown,
): Promise<HunterApplicationTruthProjection> {
  const projection = HunterApplicationTruthProjectionSchema.parse(value);
  const canonical = JSON.stringify(
    canonicalValue(projectionDigestPayload(projection)),
  );
  const computed = await sha256Hex(canonical);
  if (computed !== projection.projection_digest) {
    throw new Error(
      "Hunter Candidate Truth projection digest does not match its canonical payload",
    );
  }
  return projection;
}

export async function loadHunterTruthCache(
  store: HunterTruthCacheStore = defaultStore,
): Promise<HunterTruthCache | null> {
  const raw = await store.load();
  if (raw === null || raw === undefined) return null;
  const cache = HunterTruthCacheSchema.parse(raw);
  await verifyHunterTruthProjectionIntegrity(cache.projection);
  return cache;
}

export async function acceptHunterTruthProjection(
  value: unknown,
  store: HunterTruthCacheStore = defaultStore,
  now = new Date(),
): Promise<{
  disposition: HunterTruthUpdateDisposition;
  cache: HunterTruthCache;
}> {
  const incoming = await verifyHunterTruthProjectionIntegrity(value);
  const currentCache = await loadHunterTruthCache(store);
  const disposition = classifyHunterTruthUpdate(
    currentCache?.projection ?? null,
    incoming,
  );

  if (disposition === "STALE_INCOMING") {
    throw new Error(
      "Refusing stale Hunter Candidate Truth projection for the current Master Resume extraction",
    );
  }
  if (disposition === "CONFLICT") {
    throw new Error(
      "Hunter Candidate Truth projection conflicts with the cached candidate identity/revision",
    );
  }
  if (disposition === "UNCHANGED" && currentCache) {
    return { disposition, cache: currentCache };
  }

  const cache = HunterTruthCacheSchema.parse({
    cache_version: APPLICATION_TRUTH_CACHE_VERSION,
    source: "munshi-hr-hunter",
    cached_at: now.toISOString(),
    projection: incoming,
  });
  await store.save(cache);
  return { disposition, cache };
}

export type ApplicationFactResolution =
  | ReturnType<typeof resolveCanonicalHunterFact>
  | {
      status: "PROPOSAL_ONLY";
      key: string;
      authoritative: false;
      requires_secure_resolution: false;
      requires_hunter_promotion: true;
      value: ProfileFact["value"];
      source: string;
    };

/**
 * Candidate Truth always wins. Apply-local USER_CONFIRMED data may only fill a
 * currently unknown key as a proposal awaiting explicit Hunter promotion; it
 * can never overwrite a Hunter canonical or protected fact.
 */
export function resolveApplicationFact(
  projectionValue: unknown,
  key: string,
  localProposalValue?: unknown,
): ApplicationFactResolution {
  const canonical = resolveCanonicalHunterFact(projectionValue, key);
  if (canonical.status !== "UNKNOWN") return canonical;
  if (localProposalValue === undefined || localProposalValue === null) {
    return canonical;
  }

  const proposal = ProfileFactSchema.parse(localProposalValue);
  if (proposal.key !== key || proposal.trustLevel !== "USER_CONFIRMED") {
    return canonical;
  }
  return {
    status: "PROPOSAL_ONLY",
    key,
    authoritative: false,
    requires_secure_resolution: false,
    requires_hunter_promotion: true,
    value: proposal.value,
    source: proposal.source,
  };
}
