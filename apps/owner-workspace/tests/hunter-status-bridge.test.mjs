import assert from "node:assert/strict";
import test from "node:test";
import { proxyHunterStatus } from "../app/api/hunter-status/bridge.ts";

const config = {
  origin: "https://dashboard.munshi.systems",
  secret: "synthetic-backend-only-secret-strong-enough",
  allowedWorkspace: "workspace-owner",
};
const candidate = {
  version: "munshi-application-provider-summary-v1",
  job_id: 100,
  application_id: "application-exact-123",
  route_id: "route-exact-123",
  engine: "TSENTA",
  provider_state: "PROVIDER_SUBMITTED",
  status_label: "Provider reports submitted",
  employer_receipt_confirmed: false,
  attempt_count: 2,
  updated_at: "2026-10-15T00:00:00Z",
  raw_candidate_data_included: false,
  submission_authority: false,
  hiddenApplicantEmail: "must-not-be-projected@example.com",
};
const response = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });

test("exact workspace and application returns only sanitized status", async () => {
  let requested = false;
  const f = async (url, init) => {
    requested = true;
    assert.equal(url.origin, config.origin);
    assert.equal(url.pathname,
      "/api/application-provider-status/by-application/application-exact-123");
    assert.equal(init.headers["X-Hunter-Secret"], config.secret);
    assert.equal(init.method, "GET");
    return response(candidate);
  };
  const result = await proxyHunterStatus(
    "workspace-owner", "application-exact-123", config, f
  );
  assert.equal(result.status, 200);
  const body = await result.json();
  assert.ok(requested);
  assert.equal(body.engine, "TSENTA");
  assert.equal(body.employer_receipt_confirmed, false);
  assert.equal(body.submission_authority, false);
  assert.equal(result.headers.get("cache-control"), "no-store");
  assert.ok(!JSON.stringify(body).includes("hiddenApplicantEmail"));
});

test("other workspace is rejected before any upstream call", async () => {
  const result = await proxyHunterStatus(
    "workspace-attacker", "application-exact-123", config,
    async () => { throw new Error("must not call"); }
  );
  assert.equal(result.status, 403);
});

test("missing or unsafe upstream origin fails closed", async () => {
  for (const origin of [
    "http://dashboard.munshi.systems",
    "https://evil.example",
    "http://127.0.0.1:8080",
    "https://dashboard.munshi.systems.evil.com",
    "https://user:pass@dashboard.munshi.systems",
  ]) {
    const result = await proxyHunterStatus(
      "workspace-owner", "application-exact-123",
      { ...config, origin },
      async () => { throw new Error("must not call"); },
    );
    assert.equal(result.status, 503);
  }
});

test("rejects nonexact application and false receipt", async () => {
  const f = async () => response({
    ...candidate, application_id: "application-different"
  });
  const wrong = await proxyHunterStatus(
    "workspace-owner", "application-exact-123", config, f
  );
  assert.equal(wrong.status, 502);

  const fakeReceipt = await proxyHunterStatus(
    "workspace-owner", "application-exact-123", config,
    async () => response({
      ...candidate, employer_receipt_confirmed: true
    }),
  );
  assert.equal(fakeReceipt.status, 502);
});

test("backend 401, 404, HTML, or oversized payload never leaks details", async () => {
  const upstreams = [
    { status: 503, response: async () => response({ email: "secret" }, 401) },
    { status: 404, response: async () => response({}, 404) },
    { status: 502, response: async () => new Response("<html>Basic Auth</html>") },
    { status: 502, response: async () => response({ data: "x".repeat(40_000) }) },
  ];
  for (const upstream of upstreams) {
    const result = await proxyHunterStatus(
      "workspace-owner", "application-exact-123", config, upstream.response
    );
    assert.equal(result.status, upstream.status);
    assert.ok(!(await result.text()).includes("secret"));
  }
});
