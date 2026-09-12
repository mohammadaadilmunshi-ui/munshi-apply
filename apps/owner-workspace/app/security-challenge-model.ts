import type { DecryptedEntity } from "./vault-client";

export type SecurityChallengeKind =
  | "CAPTCHA"
  | "MFA"
  | "OTP"
  | "IDENTITY_VERIFICATION"
  | "AUTHENTICATION"
  | "SECURITY_CHECK";

export type SecurityChallengeCheckpoint = {
  entityId: string;
  sequence: number;
  pageId: string;
  applicationId: string | null;
  jobId: string | null;
  title: string;
  url: string;
  origin: string;
  kind: SecurityChallengeKind;
  detectedAt: string;
  expiresAt: string;
};

const CHECKPOINT_TTL_MS = 30 * 60 * 1000;

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function challengeKind(value: unknown): SecurityChallengeKind | null {
  if (value === null || value === undefined || value === false || value === "") {
    return null;
  }
  const candidate = String(value).trim().toUpperCase();
  if (candidate.includes("CAPTCHA") || candidate.includes("TURNSTILE")) {
    return "CAPTCHA";
  }
  if (candidate.includes("OTP") || candidate.includes("ONE_TIME")) return "OTP";
  if (candidate.includes("MFA") || candidate.includes("2FA")) return "MFA";
  if (candidate.includes("IDENTITY")) return "IDENTITY_VERIFICATION";
  if (candidate.includes("AUTH")) return "AUTHENTICATION";
  return "SECURITY_CHECK";
}

export function safeChallengeUrl(value: unknown): string | null {
  const candidate = text(value);
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function checkpointFromEntity(
  entity: DecryptedEntity,
  nowMs: number,
): SecurityChallengeCheckpoint | null {
  if (entity.event.entityType !== "APPLICATION.V1") return null;
  const payload = record(entity.value);
  if (!payload) return null;

  // APPLICATION.V1 stores the canonical ApplicationPage directly. Accept a
  // nested `page` only for older/experimental payloads so the UI can recover
  // safely across rolling upgrades.
  const page = record(payload.page) ?? payload;
  const kind = challengeKind(page.securityCheckpoint);
  const url = safeChallengeUrl(page.url ?? payload.url);
  const pageId = text(page.pageId ?? payload.pageId);
  if (!kind || !url || !pageId) return null;

  const detectedAt =
    text(payload.capturedAt) ??
    text(payload.observedAt) ??
    text(page.observedAt) ??
    entity.event.createdAt;
  const detectedMs = Date.parse(detectedAt);
  if (!Number.isFinite(detectedMs)) return null;
  if (detectedMs > nowMs + 60_000) return null;
  if (nowMs - detectedMs > CHECKPOINT_TTL_MS) return null;

  const origin = new URL(url).origin;
  return {
    entityId: entity.event.entityId,
    sequence: entity.event.sequence,
    pageId,
    applicationId: text(payload.applicationId),
    jobId: text(payload.jobId),
    title: text(page.title ?? payload.title) ?? "Job application",
    url,
    origin,
    kind,
    detectedAt: new Date(detectedMs).toISOString(),
    expiresAt: new Date(detectedMs + CHECKPOINT_TTL_MS).toISOString(),
  };
}

/**
 * Selects the newest current encrypted APPLICATION.V1 snapshot that reports a
 * security checkpoint. decryptLatestEntities() already collapses history by
 * entity id. A newer revision of the same page with securityCheckpoint=null
 * therefore clears that checkpoint instead of leaving a stale popup behind.
 */
export function deriveSecurityChallenge(
  entities: Map<string, DecryptedEntity>,
  now = new Date(),
): SecurityChallengeCheckpoint | null {
  const nowMs = now.getTime();
  const candidates = Array.from(entities.values())
    .map((entity) => checkpointFromEntity(entity, nowMs))
    .filter((value): value is SecurityChallengeCheckpoint => value !== null)
    .sort(
      (left, right) =>
        right.sequence - left.sequence ||
        right.detectedAt.localeCompare(left.detectedAt),
    );
  return candidates[0] ?? null;
}

export function challengeLabel(kind: SecurityChallengeKind): string {
  switch (kind) {
    case "CAPTCHA":
      return "CAPTCHA verification";
    case "MFA":
      return "Multi-factor authentication";
    case "OTP":
      return "One-time verification code";
    case "IDENTITY_VERIFICATION":
      return "Identity verification";
    case "AUTHENTICATION":
      return "Sign-in verification";
    default:
      return "Security verification";
  }
}
