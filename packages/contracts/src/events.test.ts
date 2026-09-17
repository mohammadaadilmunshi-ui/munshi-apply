import { describe, expect, it } from "vitest";
import { EventEnvelopeSchema } from "./index";

describe("canonical event envelope", () => {
  it("accepts the v1 external event contract", () => {
    const event = EventEnvelopeSchema.parse({
      schema_version: "1.0",
      event_id: "EVT-000001",
      correlation_id: "COR-000001",
      event_type: "APPLICATION_DETECTED",
      occurred_at: "2026-08-14T03:30:00Z",
      application_id: null,
      source: "munshi-apply",
      payload: {},
    });
    expect(event.event_id).toBe("EVT-000001");
  });

  it("rejects malformed or unversioned external events", () => {
    expect(() =>
      EventEnvelopeSchema.parse({
        event_id: "EVT-000001",
        event_type: "APPLICATION_DETECTED",
        payload: {},
      }),
    ).toThrow();
  });
});
