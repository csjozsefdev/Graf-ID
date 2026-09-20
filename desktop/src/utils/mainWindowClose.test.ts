import { beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({ onCloseRequested: vi.fn() }),
}));

import {
  requestMainWindowClose,
  resolveMainWindowCloseMode,
  setMainWindowCloseHandler,
} from "./mainWindowClose";

describe("resolveMainWindowCloseMode", () => {
  it("hides to tray while the editor lifecycle probe is active", () => {
    expect(
      resolveMainWindowCloseMode({
        editorLifecycleActive: true,
        hideToTrayUsed: false,
      })
    ).toBe("hide_tray");
  });

  it("hides to tray after a successful open-project tray handoff", () => {
    expect(
      resolveMainWindowCloseMode({
        editorLifecycleActive: false,
        hideToTrayUsed: true,
      })
    ).toBe("hide_tray");
  });

  it("quits when no tray companion workflow is active", () => {
    expect(
      resolveMainWindowCloseMode({
        editorLifecycleActive: false,
        hideToTrayUsed: false,
      })
    ).toBe("quit");
  });
});

describe("requestMainWindowClose reentrancy (L7)", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    setMainWindowCloseHandler(null);
  });

  it("ignores a second call while the first is still resolving", async () => {
    let resolveHandler: (() => void) | null = null;
    const handler = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveHandler = resolve;
        })
    );
    setMainWindowCloseHandler(handler);

    const first = requestMainWindowClose();
    const second = requestMainWindowClose();

    expect(handler).toHaveBeenCalledTimes(1);

    resolveHandler?.();
    await Promise.all([first, second]);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("allows a fresh call after the previous one has settled", async () => {
    const handler = vi.fn().mockResolvedValue(undefined);
    setMainWindowCloseHandler(handler);

    await requestMainWindowClose();
    await requestMainWindowClose();

    expect(handler).toHaveBeenCalledTimes(2);
  });

  it("clears the in-flight guard even if the handler throws", async () => {
    const handler = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined);
    setMainWindowCloseHandler(handler);

    await expect(requestMainWindowClose()).rejects.toThrow("boom");
    await requestMainWindowClose();

    expect(handler).toHaveBeenCalledTimes(2);
  });
});
