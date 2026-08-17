import { describe, expect, it } from "vitest";
import { nativeRuntimeCompatibility, type NativeRuntimeHealth } from "./client";

function health(
  capabilities: NonNullable<NativeRuntimeHealth["capabilities"]>,
): NativeRuntimeHealth {
  return {
    status: "healthy",
    database: "healthy",
    migration_count: 10,
    schema_version: "010_job_signal_intelligence.sql",
    outbox: {},
    protocol_version: 3,
    capabilities,
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
  ollama_fallback: true,
  writing_style_learning: true,
  teach_munshi_state_capture: true,
  account_orchestration: true,
  job_signal_intelligence: true,
  application_analytics: true,
};

describe("native runtime compatibility", () => {
  it("accepts the current protocol only when current orchestration capabilities exist", () => {
    expect(nativeRuntimeCompatibility(health(currentCapabilities))).toEqual({
      compatible: true,
    });
  });

  it("rejects an older protocol-v3 companion without account orchestration", () => {
    const result = nativeRuntimeCompatibility(
      health({ ...currentCapabilities, account_orchestration: false }),
    );
    expect(result.compatible).toBe(false);
    if (!result.compatible) {
      expect(result.reason).toContain("account_orchestration");
    }
  });

  it("rejects an older protocol-v3 companion without Job Signal Intelligence", () => {
    const result = nativeRuntimeCompatibility(
      health({ ...currentCapabilities, job_signal_intelligence: undefined }),
    );
    expect(result.compatible).toBe(false);
    if (!result.compatible) {
      expect(result.reason).toContain("job_signal_intelligence");
    }
  });

  it("rejects an older protocol-v3 companion without application analytics", () => {
    const result = nativeRuntimeCompatibility(
      health({ ...currentCapabilities, application_analytics: undefined }),
    );
    expect(result.compatible).toBe(false);
    if (!result.compatible) {
      expect(result.reason).toContain("application_analytics");
    }
  });

  it("still rejects an outdated native protocol before capability evaluation", () => {
    const result = nativeRuntimeCompatibility({
      ...health(currentCapabilities),
      protocol_version: 2,
    });
    expect(result).toEqual({
      compatible: false,
      reason: "Installed native protocol 2; version 3 is required.",
    });
  });
});
