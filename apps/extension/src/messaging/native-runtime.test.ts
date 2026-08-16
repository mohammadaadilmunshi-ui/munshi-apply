import { describe, expect, it } from "vitest";
import {
  REQUIRED_NATIVE_PROTOCOL_VERSION,
  nativeRuntimeCompatibility,
  type NativeRuntimeHealth,
} from "./client";

function health(input: Partial<NativeRuntimeHealth> = {}): NativeRuntimeHealth {
  return {
    status: "healthy",
    database: "healthy",
    migration_count: 6,
    schema_version: "006_ai_budget_reservations.sql",
    outbox: {},
    ...input,
  };
}

describe("native runtime compatibility", () => {
  it("rejects a legacy PING that has no protocol version", () => {
    expect(nativeRuntimeCompatibility(health())).toEqual({
      compatible: false,
      reason: "Installed native companion predates the current protocol.",
    });
  });

  it("accepts the current protocol only when required capabilities exist", () => {
    expect(
      nativeRuntimeCompatibility(
        health({
          protocol_version: REQUIRED_NATIVE_PROTOCOL_VERSION,
          capabilities: {
            profile_vault: true,
            application_checkpoints: true,
            interaction_learning: true,
            teach_munshi: true,
            ai_settings: true,
            ai_governance: true,
            ai_draft_lifecycle: true,
          },
        }),
      ),
    ).toEqual({ compatible: true });
  });
});
