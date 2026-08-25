import type { ApplicationPage } from "@munshi-apply/contracts";

export const RECENT_APPLICATION_CONTEXT_TTL_MS = 3 * 60 * 1000;

export type RecentApplicationContext = {
  page: ApplicationPage;
  capturedAt: number;
  expiresAt: number;
};

export function createRecentApplicationContext(
  page: ApplicationPage,
  now = Date.now(),
  ttlMs = RECENT_APPLICATION_CONTEXT_TTL_MS,
): RecentApplicationContext {
  const safeTtl = Math.max(1, ttlMs);
  return {
    page,
    capturedAt: now,
    expiresAt: now + safeTtl,
  };
}

export function isRecentApplicationContextFresh(
  context: RecentApplicationContext | null | undefined,
  now = Date.now(),
): context is RecentApplicationContext {
  return Boolean(
    context &&
      Number.isFinite(context.capturedAt) &&
      Number.isFinite(context.expiresAt) &&
      context.expiresAt > now &&
      context.page &&
      Number.isSafeInteger(context.page.tabId) &&
      context.page.tabId >= 0,
  );
}

export function parseRecentApplicationContext(
  value: unknown,
  now = Date.now(),
): RecentApplicationContext | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<RecentApplicationContext>;
  const context = {
    page: candidate.page,
    capturedAt: Number(candidate.capturedAt),
    expiresAt: Number(candidate.expiresAt),
  } as RecentApplicationContext;
  return isRecentApplicationContextFresh(context, now) ? context : null;
}

export function recentContextBelongsToTab(
  context: RecentApplicationContext | null | undefined,
  tabId: number,
): boolean {
  return Boolean(context && context.page.tabId === tabId);
}
