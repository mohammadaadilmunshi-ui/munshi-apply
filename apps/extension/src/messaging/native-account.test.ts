import { describe, expect, it } from "vitest";
import { parseAccountRecord, parseAccountRecords } from "./native-account";

const valid = {
  accountId: "account-1",
  employer: "Example",
  domain: "example.com",
  scopeKey: "example.com",
  portalUrl: "https://example.com/candidate/login",
  email: "aadil@example.com",
  exists: true,
  createdAt: "2026-08-17T19:00:00.000Z",
  lastUsed: "2026-08-17T19:05:00.000Z",
  applicationIds: ["application-1"],
};

describe("native account registry parsing", () => {
  it("accepts the metadata-only account record contract", () => {
    expect(parseAccountRecord(valid)).toEqual(valid);
    expect(parseAccountRecords([valid])).toEqual([valid]);
  });

  it("rejects malformed account metadata", () => {
    expect(() => parseAccountRecord({ ...valid, exists: "yes" })).toThrow(
      /exists must be boolean/,
    );
    expect(() =>
      parseAccountRecord({ ...valid, applicationIds: ["application-1", 2] }),
    ).toThrow(/applicationIds are invalid/);
    expect(() => parseAccountRecord({ ...valid, lastUsed: "today" })).toThrow(
      /ISO timestamp/,
    );
  });
});
