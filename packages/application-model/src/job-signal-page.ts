import type { ApplicationPage } from "@munshi-apply/contracts";
import { applicationUrlIdentityKey } from "./application-url";
import type { JobSignalInput } from "./job-signals";

export type PageJobSignalOptions = {
  applicationId?: string;
  accountRequired?: boolean;
  manualRequiredControls?: number;
};

export type PageJobSignalSource = {
  input: JobSignalInput;
  jobId: string;
  sourceIdentity: string;
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
  const manualRequiredControls = normalizedManualCount(
    options.manualRequiredControls,
  );
  const accountRequired = options.accountRequired === true;
  const validationErrors = page.validationErrorCount;
  const hasObservedFriction =
    accountRequired || manualRequiredControls > 0 || validationErrors > 0;
  const frictionIdentity = hasObservedFriction
    ? [
        accountRequired ? "account" : "no-account",
        manualRequiredControls,
        validationErrors,
      ].join(":")
    : "no-observed-friction";
  const sourceIdentity = applicationUrlIdentityKey(page.url);
  const stableApplicationIdentity = compact(options.applicationId);
  const jobIdentityMaterial = stableApplicationIdentity || sourceIdentity;
  const jobId = `job-${stableHash(`job-identity-v1\n${jobIdentityMaterial}`)}`;
  const fingerprintMaterial = [
    "job-signal-page-v2",
    sourceIdentity,
    page.applicationState,
    jobContext,
    frictionIdentity,
  ].join("\n");

  return {
    input: {
      description: jobContext || null,
      applicationFriction: hasObservedFriction
        ? {
            accountRequired,
            manualRequiredControls,
            validationErrors,
          }
        : null,
    },
    jobId,
    sourceIdentity,
    sourceFingerprint: `job-source-${stableHash(fingerprintMaterial)}`,
  };
}
