import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchCloudEvents, getCloudHealth } from "./cloud";

const connection = {
  baseUrl: "https://workspace.example",
  deviceId: "device-responsive",
  credential: "credential-responsive",
  platform: "macos-edge",
  connectedAt: "2026-08-26T00:00:00.000Z",
};

function installHangingFetch() {
  const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      });
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("cloud responsiveness", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("bounds a hanging cloud event download", async () => {
    vi.useFakeTimers();
    installHangingFetch();

    const pending = fetchCloudEvents(connection, 0);
    const rejection = expect(pending).rejects.toThrow(
      "Encrypted workspace event download timed out after 5 seconds",
    );
    await vi.advanceTimersByTimeAsync(5_000);
    await rejection;
  });

  it("coalesces concurrent health checks instead of stacking network work", async () => {
    vi.useFakeTimers();
    const fetchMock = installHangingFetch();

    const first = getCloudHealth(connection);
    const second = getCloudHealth(connection);
    expect(first).toBe(second);

    const firstRejection = expect(first).rejects.toThrow(
      "Encrypted workspace check timed out",
    );
    const secondRejection = expect(second).rejects.toThrow(
      "Encrypted workspace check timed out",
    );
    await vi.advanceTimersByTimeAsync(5_000);
    await Promise.all([firstRejection, secondRejection]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
