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
    migration_count: 11,
    schema_version: "011_job_signal_identity_and_analytics.sql",
    outbox: {},
    ...input,
  };
}

const currentCapabilities: NonNullable<NativeRuntimeHealth["capabilities"]> = {
  profile_vault: true,
  application_checkpoints: true,
  interaction_learning: true,
  teach_munshi: true,
  ai_settings: true,
  ai_governance: true,
  ai_draft_lifecycle: true,
  document_evidence_ingestion: true,
  provider_routing: true,
  writing_style_learning: true,
  account_orchestration: true,
  job_signal_intelligence: true,
  job_signal_identity_binding: true,
  application_analytics: true,
};

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
          capabilities: currentCapabilities,
        }),
      ),
    ).toEqual({ compatible: true });
  });

  it("rejects protocol v3 companions that predate application analytics", () => {
    expect(
      nativeRuntimeCompatibility(
        health({
          protocol_version: REQUIRED_NATIVE_PROTOCOL_VERSION,
          capabilities: {
            ...currentCapabilities,
            application_analytics: false,
          },
        }),
      ),
    ).toEqual({
      compatible: false,
      reason:
        "Native companion is missing required capabilities: application_analytics.",
    });
  });
});
