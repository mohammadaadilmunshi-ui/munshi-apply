import { describe, expect, it } from "vitest";
import {
  localProfileSaveAck,
  parseProfileSaveAck,
  syncedProfileSaveAck,
} from "./profile-save-ack";

describe("profile save acknowledgement", () => {
  it("marks a local-only save as not cloud synchronized", () => {
    expect(localProfileSaveAck()).toEqual({
      localSaved: true,
      cloudSynced: false,
      conflict: null,
    });
  });

  it("preserves a protected-profile conflict on the local save acknowledgement", () => {
    const conflict = {
      keys: ["work_authorization"],
      details: [
        {
          key: "work_authorization",
          localValue: "local",
          remoteValue: "remote",
        },
      ],
      detectedAt: "2026-08-17T21:00:00.000Z",
    };
    expect(localProfileSaveAck(conflict)).toEqual({
      localSaved: true,
      cloudSynced: false,
      conflict,
    });
  });

  it("marks only an acknowledged encrypted save as synchronized", () => {
    expect(syncedProfileSaveAck()).toEqual({
      localSaved: true,
      cloudSynced: true,
      conflict: null,
    });
  });

  it("rejects missing or contradictory acknowledgements", () => {
    expect(() => parseProfileSaveAck(undefined)).toThrow(
      "Profile save returned no acknowledgement",
    );
    expect(() =>
      parseProfileSaveAck({
        localSaved: true,
        cloudSynced: true,
        conflict: {
          keys: ["first_name"],
          details: [],
          detectedAt: "2026-08-17T21:00:00.000Z",
        },
      }),
    ).toThrow("cannot be synced while a conflict is unresolved");
  });
});
