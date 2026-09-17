import { describe, expect, it, vi } from "vitest";
import { NativeHealthStabilizer } from "./native-health-stabilizer";

describe("native health stabilizer", () => {
  it("retries a transient failure before reporting the companion unavailable", async () => {
    const send = vi
      .fn<() => Promise<unknown>>()
      .mockResolvedValueOnce({ ok: false, error: "port closed" })
      .mockResolvedValueOnce({ ok: true, data: { status: "healthy" } });
    const stabilizer = new NativeHealthStabilizer(() => 1_000, [0], 30_000);

    const response = await stabilizer.request(send, async () => undefined);

    expect(send).toHaveBeenCalledTimes(2);
    expect(response).toEqual({ ok: true, data: { status: "healthy" } });
  });

  it("uses the last known healthy response for a brief transport hiccup", async () => {
    let now = 1_000;
    const stabilizer = new NativeHealthStabilizer(() => now, [], 30_000);
    await stabilizer.request(
      async () => ({ ok: true, data: { status: "healthy" } }),
      async () => undefined,
    );
    now += 5_000;

    const response = await stabilizer.request(
      async () => ({ ok: false, error: "temporary disconnect" }),
      async () => undefined,
    );

    expect(response).toEqual({ ok: true, data: { status: "healthy" } });
  });
});
