/** Privacy-minimized, server-only bridge to Hunter's exact application status. */

const identity = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const states = new Set([
  "PREPARATION", "FILLING", "PAUSED", "FAILED",
  "PROVIDER_SUBMITTED", "EMPLOYER_CONFIRMED",
]);

export type HunterProviderStatus = {
  version: "munshi-application-provider-summary-v1";
  application_id: string;
  job_id: number;
  route_id: string;
  engine: "NATIVE" | "TSENTA";
  provider_state: string;
  status_label: string;
  employer_receipt_confirmed: boolean;
  attempt_count: number;
  updated_at: string | null;
  raw_candidate_data_included: false;
  submission_authority: false;
};

export type BridgeEnvironment = {
  origin?: string;
  secret?: string;
  allowedWorkspace?: string;
};

function validateOrigin(raw: string): string | null {
  try {
    const parsed = new URL(raw);
    if (
      parsed.protocol !== "https:" ||
      (!parsed.hostname.endsWith(".munshi.systems") &&
        parsed.hostname !== "munshi.systems") ||
      parsed.port ||
      parsed.username || parsed.password ||
      parsed.search || parsed.hash ||
      (parsed.pathname !== "/" && parsed.pathname !== "")
    ) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function sanitizedStatus(raw: unknown, expectedId: string): HunterProviderStatus | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (
    value.version !== "munshi-application-provider-summary-v1" ||
    value.application_id !== expectedId ||
    !Number.isSafeInteger(value.job_id) ||
    !identity.test(String(value.route_id ?? "")) ||
    !["NATIVE", "TSENTA"].includes(String(value.engine ?? "")) ||
    !states.has(String(value.provider_state ?? "")) ||
    typeof value.employer_receipt_confirmed !== "boolean" ||
    !Number.isSafeInteger(value.attempt_count) ||
    Number(value.attempt_count) < 0 ||
    value.raw_candidate_data_included !== false ||
    value.submission_authority !== false
  ) return null;
  // Never accept a confirmed receipt with no confirmed provider state.
  if (value.employer_receipt_confirmed &&
      value.provider_state !== "EMPLOYER_CONFIRMED") return null;
  return {
    version: "munshi-application-provider-summary-v1",
    application_id: expectedId,
    job_id: Number(value.job_id),
    route_id: String(value.route_id),
    engine: value.engine as "NATIVE" | "TSENTA",
    provider_state: String(value.provider_state),
    status_label:
      value.provider_state === "EMPLOYER_CONFIRMED" && value.employer_receipt_confirmed
        ? "Employer confirmation verified"
        : value.provider_state === "PROVIDER_SUBMITTED"
          ? "Provider reports submitted — receipt not verified"
          : value.provider_state === "FAILED" ? "Stopped safely"
          : value.provider_state === "PAUSED" ? "Needs attention"
          : "Application preparation in progress",
    employer_receipt_confirmed: value.employer_receipt_confirmed as boolean,
    attempt_count: Number(value.attempt_count),
    updated_at: typeof value.updated_at === "string" ? value.updated_at.slice(0, 40) : null,
    raw_candidate_data_included: false,
    submission_authority: false,
  };
}

export async function proxyHunterStatus(
  workspaceId: string,
  applicationId: string,
  config: BridgeEnvironment,
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  const noStore = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
  if (!identity.test(applicationId)) {
    return Response.json({ error: "Invalid application identity." }, { status: 400, headers: noStore });
  }
  if (!config.allowedWorkspace || config.allowedWorkspace !== workspaceId) {
    return Response.json({ error: "Workspace is not linked to the Hunter owner." }, { status: 403, headers: noStore });
  }
  const origin = validateOrigin(config.origin ?? "");
  if (!origin || !config.secret || config.secret.length < 24) {
    return Response.json({ error: "Hunter provider bridge is not configured." }, { status: 503, headers: noStore });
  }
  try {
    const upstream = await fetcher(
      new URL(
        "/api/application-provider-status/by-application/" + encodeURIComponent(applicationId),
        origin,
      ),
      {
        method: "GET",
        headers: {
          "X-Hunter-Secret": config.secret,
          "Accept": "application/json",
        },
        redirect: "manual",
        cache: "no-store",
        signal: AbortSignal.timeout(6_000),
      },
    );
    if (upstream.status === 404) {
      return Response.json({ error: "No exact Hunter application match." }, { status: 404, headers: noStore });
    }
    if (upstream.status !== 200) {
      return Response.json({ error: "Hunter provider status is unavailable." }, { status: 503, headers: noStore });
    }
    const contentType = upstream.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      return Response.json({ error: "Hunter returned an unexpected response." }, { status: 502, headers: noStore });
    }
    // Stream in bounded chunks; a trusted-looking upstream must not force an
    // unbounded response allocation in the owner's Cloudflare worker.
    const responseBody = upstream.body;
    if (!responseBody) {
      return Response.json({ error: "Hunter response was empty." }, { status: 502, headers: noStore });
    }
    const reader = responseBody.getReader();
    let size = 0;
    const chunks: Uint8Array[] = [];
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 32_000) {
          await reader.cancel();
          return Response.json({ error: "Hunter response exceeded safe bounds." }, { status: 502, headers: noStore });
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const complete = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      complete.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const normalized = sanitizedStatus(
      JSON.parse(new TextDecoder().decode(complete)), applicationId,
    );
    if (!normalized) {
      return Response.json({ error: "Hunter status contract mismatch." }, { status: 502, headers: noStore });
    }
    return Response.json(normalized, { headers: noStore });
  } catch {
    return Response.json({ error: "Hunter provider status is unavailable." }, { status: 503, headers: noStore });
  }
}
