import type { ApplicationPage } from "@munshi-apply/contracts";
import type { JobSignalInput } from "./job-signals";

export type PageJobSignalOptions = {
  accountRequired?: boolean;
  manualRequiredControls?: number;
};

export type PageJobSignalSource = {
  input: JobSignalInput;
  sourceFingerprint: string;
};

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function stableHash(value: string): string {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0).toString(36);
}

function sourceUrl(rawUrl: string): string {
  const url = new URL(rawUrl);
  url.hash = "";
  return `${url.origin.toLocaleLowerCase("en-US")}${url.pathname}`;
}

function normalizedManualCount(value: number | undefined): number {
  return Number.isSafeInteger(value) && Number(value) > 0 ? Number(value) : 0;
}

/**
 * Browser/application pages do not currently expose authoritative structured
 * job facts such as role, company, compensation, or location. Preserve those
 * fields as unknown rather than inferring them from a browser title or form
 * question. Free-text job analysis is allowed only on the explicit JOB_CONTEXT
 * state; application questions remain separate from employer/job evidence.
 */
export function buildPageJobSignalSource(
  page: ApplicationPage,
  options: PageJobSignalOptions = {},
): PageJobSignalSource {
  const jobContext =
    page.applicationState === "JOB_CONTEXT" ? compact(page.pageContext) : "";
  const pageIdentity = compact(page.pageFingerprint) || sourceUrl(page.url);
  const fingerprintMaterial = [
    "job-signal-page-v1",
    sourceUrl(page.url),
    page.applicationState,
    pageIdentity,
    jobContext,
  ].join("\n");

  return {
    input: {
      description: jobContext || null,
      applicationFriction: {
        accountRequired: options.accountRequired === true,
        manualRequiredControls: normalizedManualCount(
          options.manualRequiredControls,
        ),
        validationErrors: page.validationErrorCount,
      },
    },
    sourceFingerprint: `job-source-${stableHash(fingerprintMaterial)}`,
  };
}
