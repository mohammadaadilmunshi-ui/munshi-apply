import { isEligibleApplicationPage } from "@munshi-apply/application-model";
import type { ApplicationPage } from "@munshi-apply/contracts";

const storagePrefix = "job-context-v1:";
const maxListingCharacters = 12_000;
const maxApplicationCharacters = 7_000;
const maxAgeMilliseconds = 2 * 60 * 60 * 1_000;
const careerContextPattern = /\b(career|careers|job|jobs|recruit|recruiting|position|vacancy|opportunit)/i;
const descriptionSignalPattern = /\b(responsibilit|qualification|requirements?|what you(?:'|’)ll do|what we(?:'|’)re looking for|about the role|job description|role overview|preferred qualifications?)\b/i;

export type StoredJobContext = {
  url: string;
  title: string;
  pageContext: string;
  capturedAt: string;
};

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function storageKey(tabId: number): string {
  return `${storagePrefix}${tabId}`;
}

export function shouldRememberJobContext(page: ApplicationPage): boolean {
  if (isEligibleApplicationPage(page)) return false;
  const context = compact(page.pageContext);
  if (context.length < 500) return false;
  let urlContext = "";
  try {
    const url = new URL(page.url);
    urlContext = `${url.hostname} ${url.pathname} ${url.search}`;
  } catch {
    return false;
  }
  const combined = `${urlContext} ${page.title} ${context.slice(0, 8_000)}`;
  return careerContextPattern.test(combined) && descriptionSignalPattern.test(combined);
}

export function mergeJobContext(
  page: ApplicationPage,
  stored: StoredJobContext | null,
  now = Date.now(),
): ApplicationPage {
  if (!stored) return page;
  const capturedAt = Date.parse(stored.capturedAt);
  if (!Number.isFinite(capturedAt) || now - capturedAt > maxAgeMilliseconds) {
    return page;
  }
  if (stored.url === page.url) return page;
  const listing = compact(stored.pageContext).slice(0, maxListingCharacters);
  if (!listing) return page;
  const current = compact(page.pageContext).slice(0, maxApplicationCharacters);
  const pageContext = compact(
    `Job listing context captured before the application: ${stored.title}. ${listing} Current application page context: ${current}`,
  ).slice(0, 20_000);
  return { ...page, pageContext };
}

export async function rememberJobContext(
  tabId: number,
  page: ApplicationPage,
): Promise<void> {
  if (!shouldRememberJobContext(page)) return;
  const record: StoredJobContext = {
    url: page.url,
    title: page.title,
    pageContext: compact(page.pageContext).slice(0, maxListingCharacters),
    capturedAt: new Date().toISOString(),
  };
  await chrome.storage.session.set({ [storageKey(tabId)]: record });
}

export async function readJobContext(
  tabId: number,
): Promise<StoredJobContext | null> {
  const key = storageKey(tabId);
  const stored = await chrome.storage.session.get(key);
  const candidate = stored[key];
  if (!candidate || typeof candidate !== "object") return null;
  const value = candidate as Partial<StoredJobContext>;
  if (
    typeof value.url !== "string" ||
    typeof value.title !== "string" ||
    typeof value.pageContext !== "string" ||
    typeof value.capturedAt !== "string"
  ) {
    return null;
  }
  return value as StoredJobContext;
}

export async function clearJobContext(tabId: number): Promise<void> {
  await chrome.storage.session.remove(storageKey(tabId));
}
