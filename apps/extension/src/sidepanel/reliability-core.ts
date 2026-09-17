import { isEligibleApplicationPage } from "@munshi-apply/application-model";
import type { ApplicationPage } from "@munshi-apply/contracts";

export const RECENT_JOB_CONTEXT_GRACE_MS = 3 * 60 * 1_000;

const careerContextPattern =
  /\b(career|careers|job|jobs|recruit|recruiting|position|vacancy|opportunit)/i;
const descriptionSignalPattern =
  /\b(responsibilit|qualification|requirements?|what you(?:'|’)ll do|what we(?:'|’)re looking for|about the role|job description|role overview|preferred qualifications?)\b/i;

export type RecentJobContextKind = "APPLICATION" | "LISTING";

export type RecentJobContextRecord = {
  page: ApplicationPage;
  kind: RecentJobContextKind;
  capturedAt: number;
  retainedUntil: number | null;
};

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

export function classifyJobContext(
  page: ApplicationPage,
): RecentJobContextKind | null {
  if (isEligibleApplicationPage(page)) return "APPLICATION";
  const context = compact(page.pageContext);
  if (context.length < 500) return null;
  let locator = "";
  try {
    const url = new URL(page.url);
    locator = `${url.hostname} ${url.pathname} ${url.search}`;
  } catch {
    return null;
  }
  const combined = `${locator} ${page.title} ${context.slice(0, 8_000)}`;
  return careerContextPattern.test(combined) &&
    descriptionSignalPattern.test(combined)
    ? "LISTING"
    : null;
}

export function beginRecentContextRetention(
  record: RecentJobContextRecord,
  now = Date.now(),
): RecentJobContextRecord {
  return {
    ...record,
    retainedUntil: now + RECENT_JOB_CONTEXT_GRACE_MS,
  };
}

export function remainingRecentContextMs(
  record: RecentJobContextRecord,
  now = Date.now(),
): number {
  if (record.retainedUntil === null) return Number.POSITIVE_INFINITY;
  return Math.max(0, record.retainedUntil - now);
}

export function recentContextIsVisible(
  record: RecentJobContextRecord,
  now = Date.now(),
): boolean {
  return remainingRecentContextMs(record, now) > 0;
}

export function humanizeSemanticType(value: string): string {
  return value
    .toLocaleLowerCase("en-US")
    .replaceAll("_", " ")
    .replace(/^\w/, (letter) => letter.toUpperCase());
}
