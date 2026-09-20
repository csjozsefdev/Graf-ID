import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TimeoutError, withTimeout } from "./withTimeout";

describe("withTimeout", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves with the underlying value when it settles before the deadline", async () => {
    const inner = Promise.resolve("ok");
    const result = withTimeout(inner, 1000, "should not fire");
    await vi.advanceTimersByTimeAsync(0);
    await expect(result).resolves.toBe("ok");
  });

  it("rejects with TimeoutError once the deadline elapses without the inner promise settling (H7/H8)", async () => {
    let neverResolve: (value: unknown) => void = () => {};
    const inner = new Promise((resolve) => {
      neverResolve = resolve;
    });
    const result = withTimeout(inner, 1000, "Open Project did not respond in time.");

    const assertion = expect(result).rejects.toBeInstanceOf(TimeoutError);
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;

    // Cleanup: if the inner promise resolves later, nothing should throw.
    neverResolve("late");
  });

  it("TimeoutError message carries the caller's detail with a timeout: prefix (for errors.ts's parseErrorCode)", async () => {
    const inner = new Promise(() => {});
    const result = withTimeout(inner, 500, "Closing the session did not respond in time.");
    const promise = result.catch((err) => err);
    await vi.advanceTimersByTimeAsync(500);
    const err = await promise;
    expect(err).toBeInstanceOf(TimeoutError);
    expect((err as Error).message).toBe("timeout: Closing the session did not respond in time.");
  });

  it("rejects with the inner promise's own error when it fails before the deadline", async () => {
    const inner = Promise.reject(new Error("boom"));
    const result = withTimeout(inner, 1000, "should not fire");
    await expect(result).rejects.toThrow("boom");
  });

  it("does not fire the timeout after the inner promise already resolved", async () => {
    const inner = Promise.resolve("fast");
    const result = withTimeout(inner, 1000, "should not fire");
    await expect(result).resolves.toBe("fast");
    // Advancing time afterward must not produce an unhandled rejection.
    await vi.advanceTimersByTimeAsync(2000);
  });
});
