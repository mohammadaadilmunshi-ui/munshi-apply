import { describe, expect, it } from "vitest";
import { assertTransition, canTransition } from "./index";

describe("application state model", () => {
  it("supports dynamically omitted workflow states", () => {
    expect(canTransition("JOB_CONTEXT", "QUESTIONS")).toBe(true);
  });

  it("blocks unsafe backward transitions", () => {
    expect(() => assertTransition("SUBMISSION", "PERSONAL")).toThrow(
      "Invalid application transition",
    );
  });
});
