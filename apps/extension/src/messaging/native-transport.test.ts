import { afterEach, describe, expect, it, vi } from "vitest";
import { createNativeRequestBroker } from "./native-transport";

type MessageListener = (message: unknown) => void;
type DisconnectListener = () => void;

function fakePort() {
  const messageListeners: MessageListener[] = [];
  const disconnectListeners: DisconnectListener[] = [];
  const sent: unknown[] = [];
  let disconnects = 0;

  return {
    port: {
      postMessage(message: unknown) {
        sent.push(message);
      },
      disconnect() {
        disconnects += 1;
      },
      onMessage: {
        addListener(listener: MessageListener) {
          messageListeners.push(listener);
        },
      },
      onDisconnect: {
        addListener(listener: DisconnectListener) {
          disconnectListeners.push(listener);
        },
      },
    } as unknown as chrome.runtime.Port,
    sent,
    emitMessage(message: unknown) {
      for (const listener of messageListeners) listener(message);
    },
    emitDisconnect() {
      for (const listener of disconnectListeners) listener();
    },
    disconnectCount() {
      return disconnects;
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("native request broker", () => {
  it("serializes concurrent requests over one native port", async () => {
    vi.useFakeTimers();
    const connection = fakePort();
    const connect = vi.fn(() => connection.port);
    const broker = createNativeRequestBroker({
      connect,
      idleDisconnectMilliseconds: 25,
    });

    const first = broker.request<string>({ type: "FIRST" });
    const second = broker.request<string>({ type: "SECOND" });

    expect(connect).toHaveBeenCalledTimes(1);
    expect(connection.sent).toEqual([{ type: "FIRST" }]);

    connection.emitMessage({ ok: true, data: "one" });
    await expect(first).resolves.toBe("one");
    expect(connection.sent).toEqual([{ type: "FIRST" }, { type: "SECOND" }]);

    connection.emitMessage({ ok: true, data: "two" });
    await expect(second).resolves.toBe("two");
    expect(connect).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(25);
    expect(connection.disconnectCount()).toBe(1);
    broker.dispose();
  });

  it("rejects the active request and reconnects once for queued work", async () => {
    const firstConnection = fakePort();
    const secondConnection = fakePort();
    const connect = vi
      .fn<() => chrome.runtime.Port>()
      .mockReturnValueOnce(firstConnection.port)
      .mockReturnValueOnce(secondConnection.port);
    const broker = createNativeRequestBroker({
      connect,
      getLastErrorMessage: () => "native host exited",
      idleDisconnectMilliseconds: 10_000,
    });

    const first = broker.request<string>({ type: "FIRST" });
    const second = broker.request<string>({ type: "SECOND" });

    firstConnection.emitDisconnect();
    await expect(first).rejects.toThrow("native host exited");
    expect(connect).toHaveBeenCalledTimes(2);
    expect(secondConnection.sent).toEqual([{ type: "SECOND" }]);

    secondConnection.emitMessage({ ok: true, data: "two" });
    await expect(second).resolves.toBe("two");
    broker.dispose();
  });
});
