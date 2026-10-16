import type { CloudConnection } from "./cloud";

export type HunterProviderState = {
  version: "munshi-application-provider-summary-v1";
  application_id: string;
  job_id: number;
  route_id: string;
  engine: "NATIVE" | "TSENTA";
  provider_state: "PREPARATION" | "FILLING" | "PAUSED" | "FAILED" |
    "PROVIDER_SUBMITTED" | "EMPLOYER_CONFIRMED";
  status_label: string;
  employer_receipt_confirmed: boolean;
  attempt_count: number;
  updated_at: string | null;
  submission_authority: false;
};

export type HunterProviderResult =
  | { phase: "linked"; status: HunterProviderState }
  | { phase: "not-linked" | "unavailable"; status?: never };

const exactApplication = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const knownStates = new Set([
  "PREPARATION", "FILLING", "PAUSED", "FAILED",
  "PROVIDER_SUBMITTED", "EMPLOYER_CONFIRMED",
]);

export async function getHunterProviderState(
  connection: CloudConnection,
  applicationId: string,
): Promise<HunterProviderResult> {
  if (!exactApplication.test(applicationId)) return { phase: "not-linked" };
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6_000);
    let response: Response;
    try {
      response = await fetch(
        connection.baseUrl + "/api/hunter-status?applicationId=" +
          encodeURIComponent(applicationId),
        {
          headers: {
            "Accept": "application/json",
            "Authorization": "Bearer " + connection.credential,
          },
          signal: controller.signal,
          cache: "no-store",
        },
      );
    } finally {
      clearTimeout(timeout);
    }
    if (response.status === 404) return { phase: "not-linked" };
    if (!response.ok) return { phase: "unavailable" };
    const json: unknown = await response.json();
    if (!json || typeof json !== "object") return { phase: "unavailable" };
    const value = json as Record<string, unknown>;
    if (
      value.version !== "munshi-application-provider-summary-v1" ||
      value.application_id !== applicationId ||
      !Number.isSafeInteger(value.job_id) ||
      typeof value.route_id !== "string" ||
      !exactApplication.test(value.route_id) ||
      !["NATIVE", "TSENTA"].includes(String(value.engine)) ||
      !knownStates.has(String(value.provider_state)) ||
      !Number.isSafeInteger(value.attempt_count) ||
      typeof value.employer_receipt_confirmed !== "boolean" ||
      value.submission_authority !== false
    ) return { phase: "unavailable" };
    if (
      value.employer_receipt_confirmed === true &&
      value.provider_state !== "EMPLOYER_CONFIRMED"
    ) return { phase: "unavailable" };
    return {
      phase: "linked",
      status: {
        version: "munshi-application-provider-summary-v1",
        application_id: applicationId,
        job_id: Number(value.job_id),
        route_id: value.route_id,
        engine: value.engine as HunterProviderState["engine"],
        provider_state: value.provider_state as HunterProviderState["provider_state"],
        status_label: value.provider_state === "PROVIDER_SUBMITTED"
          ? "Provider reports submitted (receipt not verified)"
          : value.provider_state === "EMPLOYER_CONFIRMED" &&
            value.employer_receipt_confirmed === true
            ? "Employer confirmation verified"
            : String(value.status_label ?? "Application status pending").slice(0, 96),
        employer_receipt_confirmed: value.employer_receipt_confirmed as boolean,
        attempt_count: Number(value.attempt_count),
        updated_at: typeof value.updated_at === "string"
          ? value.updated_at.slice(0, 40) : null,
        submission_authority: false,
      },
    };
  } catch {
    return { phase: "unavailable" };
  }
}
