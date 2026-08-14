import { describe, expect, it } from "vitest";
import {
  normalizeBaseUrl,
  parsePairingBundle,
  validateResumeFile,
} from "./cloud";

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

describe("resume upload validation", () => {
  it("accepts supported resume formats", () => {
    expect(() =>
      validateResumeFile({
        name: "resume.pdf",
        size: 1024,
        type: "application/pdf",
      }),
    ).not.toThrow();
    expect(() =>
      validateResumeFile({
        name: "resume.docx",
        size: 2048,
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    ).not.toThrow();
  });

  it("rejects unsupported extensions and MIME types", () => {
    expect(() =>
      validateResumeFile({ name: "resume.txt", size: 100, type: "text/plain" }),
    ).toThrow("PDF, DOC, or DOCX");
    expect(() =>
      validateResumeFile({ name: "resume.pdf", size: 100, type: "text/plain" }),
    ).toThrow("file type");
  });

  it("rejects empty and oversized files", () => {
    expect(() =>
      validateResumeFile({
        name: "resume.pdf",
        size: 0,
        type: "application/pdf",
      }),
    ).toThrow("between 1 byte and 12 MB");
    expect(() =>
      validateResumeFile({
        name: "resume.pdf",
        size: 12 * 1024 * 1024 + 1,
        type: "application/pdf",
      }),
    ).toThrow("between 1 byte and 12 MB");
  });
});
