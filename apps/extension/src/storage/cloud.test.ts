import { describe, expect, it } from "vitest";
import { normalizeBaseUrl, parsePairingBundle } from "./cloud";

describe("cloud enrollment inputs", () => {
  it("normalizes an HTTPS workspace origin", () => {
    expect(normalizeBaseUrl("https://workspace.example/private?x=1#top")).toBe(
      "https://workspace.example",
    );
  });

  it("rejects an insecure workspace origin", () => {
    expect(() => normalizeBaseUrl("http://workspace.example")).toThrow(
      "must use HTTPS",
    );
  });

  it("accepts only complete one-time pairing bundles", () => {
    const bundle = {
      challengeId: "challenge-1234",
      secret: "a".repeat(43),
    };
    expect(parsePairingBundle(JSON.stringify(bundle))).toEqual({
      ...bundle,
      workspaceKey: null,
      encryptionVersion: null,
    });
    expect(() => parsePairingBundle('{"challengeId":"short"}')).toThrow(
      "incomplete",
    );
  });

  it("accepts the owner workspace encryption key", () => {
    const bundle = {
      challengeId: "challenge-1234",
      secret: "a".repeat(43),
      workspaceKey: "b".repeat(43),
      encryptionVersion: 1,
    };
    expect(parsePairingBundle(JSON.stringify(bundle))).toEqual(bundle);
  });
});
