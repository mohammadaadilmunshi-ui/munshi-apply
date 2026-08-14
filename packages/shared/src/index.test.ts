import { describe, expect, it } from "vitest";
import { redactMetadata } from "./index";

describe("redactMetadata", () => {
  it("redacts secrets recursively", () => {
    expect(
      redactMetadata({ apiKey: "secret", nested: { sessionToken: "secret" } }),
    ).toEqual({ apiKey: "[REDACTED]", nested: { sessionToken: "[REDACTED]" } });
  });
});
