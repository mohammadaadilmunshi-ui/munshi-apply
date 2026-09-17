import { afterEach, describe, expect, it, vi } from "vitest";
import { postEncryptedEntity, type CloudConnection } from "./cloud";

const connection: CloudConnection = {
  baseUrl: "https://workspace.example",
  deviceId: "device-1",
  credential: "credential",
  platform: "mac",
  connectedAt: "2026-08-14T18:00:00.000Z",
};
const rawKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

describe("cloud version acknowledgements", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("accepts only the exact next version", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ event: { version: 4 } }, { status: 201 }),
      ),
    );

    await expect(
      postEncryptedEntity({
        connection,
        rawKey,
        entityType: "PROFILE.V1",
        entityId: "profile-1",
        baseVersion: 3,
        value: { value: "encrypted" },
      }),
    ).resolves.toBe(4);
  });

  it.each([{ event: {} }, { event: { version: 5 } }, {}])(
    "fails closed for a missing or mismatched acknowledgement",
    async (payload) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => Response.json(payload, { status: 201 })),
      );

      await expect(
        postEncryptedEntity({
          connection,
          rawKey,
          entityType: "PROFILE.V1",
          entityId: "profile-1",
          baseVersion: 3,
          value: { value: "encrypted" },
        }),
      ).rejects.toThrow("not acknowledged at the expected version");
    },
  );
});
