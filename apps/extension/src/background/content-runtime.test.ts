import { describe, expect, it, vi } from "vitest";
import {
  ensureTabContentRuntime,
  isMissingContentReceiverError,
  sendWithContentRecovery,
  type ContentRuntimeApi,
} from "./content-runtime";

function fakeApi(): ContentRuntimeApi & {
  sendMessage: ReturnType<typeof vi.fn>;
  executeScript: ReturnType<typeof vi.fn>;
} {
  return {
    sendMessage: vi.fn(),
    executeScript: vi.fn(),
  } as unknown as ContentRuntimeApi & {
    sendMessage: ReturnType<typeof vi.fn>;
    executeScript: ReturnType<typeof vi.fn>;
  };
}

describe("content runtime recovery", () => {
  it("recognizes Chromium's missing and stale receiver errors", () => {
    expect(
      isMissingContentReceiverError(
        new Error(
          "Could not establish connection. Receiving end does not exist.",
        ),
      ),
    ).toBe(true);
    expect(
      isMissingContentReceiverError(
        new Error("The message port closed before a response was received."),
      ),
    ).toBe(true);
    expect(
      isMissingContentReceiverError(new Error("Extension context invalidated.")),
    ).toBe(true);
    expect(isMissingContentReceiverError(new Error("Permission denied"))).toBe(
      false,
    );
  });

  it("does not inject while the receiver is healthy", async () => {
    const runtime = fakeApi();
    runtime.sendMessage.mockResolvedValue({ ok: true });
    await expect(
      sendWithContentRecovery(runtime, 3, 0, { type: "TEST" }),
    ).resolves.toEqual({ ok: true });
    expect(runtime.executeScript).not.toHaveBeenCalled();
  });

  it("reinjects and retries the exact missing frame", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockRejectedValueOnce(
        new Error(
          "Could not establish connection. Receiving end does not exist.",
        ),
      )
      .mockResolvedValueOnce({ result: "recovered" });
    runtime.executeScript.mockResolvedValue([{ frameId: 2 }]);

    await expect(
      sendWithContentRecovery(runtime, 7, 2, { type: "TEST" }),
    ).resolves.toEqual({ result: "recovered" });
    expect(runtime.executeScript).toHaveBeenCalledWith({
      target: { tabId: 7, frameIds: [2] },
      files: ["content/bootstrap.js"],
    });
  });

  it("recovers a stale message port the same way as a missing receiver", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockRejectedValueOnce(
        new Error("The message port closed before a response was received."),
      )
      .mockResolvedValueOnce({ result: "recovered" });
    runtime.executeScript.mockResolvedValue([{ frameId: 0 }]);

    await expect(
      sendWithContentRecovery(runtime, 7, 0, { type: "TEST" }),
    ).resolves.toEqual({ result: "recovered" });
    expect(runtime.executeScript).toHaveBeenCalledTimes(1);
  });

  it("does not hide unrelated messaging failures", async () => {
    const runtime = fakeApi();
    runtime.sendMessage.mockRejectedValue(new Error("Permission denied"));
    await expect(
      sendWithContentRecovery(runtime, 7, 0, { type: "TEST" }),
    ).rejects.toThrow("Permission denied");
    expect(runtime.executeScript).not.toHaveBeenCalled();
  });

  it("restores accessible frames after extension reload and forces scans", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockRejectedValueOnce(
        new Error(
          "Could not establish connection. Receiving end does not exist.",
        ),
      )
      .mockResolvedValue({ ok: true });
    runtime.executeScript.mockResolvedValue([{ frameId: 0 }, { frameId: 4 }]);

    await ensureTabContentRuntime(runtime, 11);
    expect(runtime.executeScript).toHaveBeenCalledWith({
      target: { tabId: 11, allFrames: true },
      files: ["content/bootstrap.js"],
    });
    expect(runtime.sendMessage).toHaveBeenCalledWith(
      11,
      { type: "CONTENT_SCAN_NOW" },
      { frameId: 0 },
    );
    expect(runtime.sendMessage).toHaveBeenCalledWith(
      11,
      { type: "CONTENT_SCAN_NOW" },
      { frameId: 4 },
    );
  });

  it("surfaces a top-frame snapshot rejection instead of pretending the scan succeeded", async () => {
    const runtime = fakeApi();
    runtime.sendMessage
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({
        ok: false,
        error: "Background rejected page snapshot",
      });

    await expect(ensureTabContentRuntime(runtime, 11)).rejects.toThrow(
      "Background rejected page snapshot",
    );
    expect(runtime.executeScript).not.toHaveBeenCalled();
  });
});
