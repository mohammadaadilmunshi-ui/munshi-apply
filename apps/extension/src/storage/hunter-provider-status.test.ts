import { afterEach, describe, expect, it, vi } from "vitest";
import { getHunterProviderState } from "./hunter-provider-status";
import type { CloudConnection } from "./cloud";

const connection: CloudConnection = {
  baseUrl: "https://munshi-apply-mobile.example",
  deviceId: "device-test",
  credential: "synthetic-workspace-credential",
  platform: "edge",
  connectedAt: "2026-10-16T00:00:00Z",
};
const status = {
  version: "munshi-application-provider-summary-v1",
  application_id: "application-exact-123",
  route_id: "route-exact-123",
  job_id: 18,
  engine: "TSENTA",
  provider_state: "PROVIDER_SUBMITTED",
  status_label: "submitted",
  employer_receipt_confirmed: false,
  attempt_count: 1,
  updated_at: "2026-10-16T00:00:00Z",
  submission_authority: false,
  raw_candidate_data_included: false,
  privateName: "never reveal this",
};

afterEach(() => vi.unstubAllGlobals());

describe("Hunter shared provider status", () => {
  it("reads through paired owner workspace and redacts private fields", async () => {
    const mocked = vi.fn(async (_url: string, options: RequestInit) => {
      expect(options.headers).toEqual({
        Accept: "application/json",
        Authorization: "Bearer synthetic-workspace-credential",
      });
      return new Response(JSON.stringify(status), {
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", mocked);
    const outcome = await getHunterProviderState(
      connection,
      "application-exact-123",
    );
    expect(outcome.phase).toBe("linked");
    if (outcome.phase !== "linked")
      throw new Error("Unexpected disconnected status");
    expect(outcome.status.status_label).toContain("receipt not verified");
    expect(outcome.status.employer_receipt_confirmed).toBe(false);
    expect(JSON.stringify(outcome)).not.toContain("privateName");
    expect(mocked).toHaveBeenCalledOnce();
  });

  it("fails closed on unknown application identity without request", async () => {
    const mocked = vi.fn();
    vi.stubGlobal("fetch", mocked);
    expect(
      (await getHunterProviderState(connection, "../candidate")).phase,
    ).toBe("not-linked");
    expect(mocked).not.toHaveBeenCalled();
  });

  it("requires a verified receipt state for confirmation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...status,
              employer_receipt_confirmed: true,
            }),
            { headers: { "content-type": "application/json" } },
          ),
      ),
    );
    expect(
      (await getHunterProviderState(connection, "application-exact-123")).phase,
    ).toBe("unavailable");
  });

  it("treats unlinked and unconfigured as different states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 404 })),
    );
    expect(
      (await getHunterProviderState(connection, "application-exact-123")).phase,
    ).toBe("not-linked");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 503 })),
    );
    expect(
      (await getHunterProviderState(connection, "application-exact-123")).phase,
    ).toBe("unavailable");
  });
});

describe("Hunter status UI privacy", () => {
  it("does not display untrusted provider status text or a false job ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...status,
              provider_state: "PAUSED",
              status_label: "Candidate private@example.com must not leak",
            }),
            { headers: { "content-type": "application/json" } },
          ),
      ),
    );
    const safe = await getHunterProviderState(
      connection,
      "application-exact-123",
    );
    expect(safe.phase).toBe("linked");
    if (safe.phase === "linked") {
      expect(safe.status.status_label).toBe("Needs attention");
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...status,
              job_id: -12,
            }),
            { headers: { "content-type": "application/json" } },
          ),
      ),
    );
    const invalid = await getHunterProviderState(
      connection,
      "application-exact-123",
    );
    expect(invalid.phase).toBe("unavailable");
  });
});
