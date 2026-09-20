import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EDITOR_READINESS_EARLY_FAILURE_POLLS,
  EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES,
  EDITOR_READINESS_OVERALL_TIMEOUT_MS,
  EDITOR_READINESS_POLL_MS,
  EDITOR_STILL_WAITING_MS,
  capturePreLaunchEditorCount,
  evaluateEditorReadiness,
  startEditorReadinessProbe,
  stopEditorReadinessProbe,
  type EditorProcessProbe,
  type ProbeEditorProcess,
} from "./editorReadinessProbe";

function probe(overrides: Partial<EditorProcessProbe> = {}): EditorProcessProbe {
  return {
    launcher_pid: 100,
    launcher_pid_alive: true,
    editor_image: "Cursor.exe",
    editor_process_count: 1,
    ...overrides,
  };
}

describe("evaluateEditorReadiness", () => {
  it("returns ready when editor process count increases", () => {
    expect(
      evaluateEditorReadiness(
        probe({ editor_process_count: 3 }),
        { preLaunchEditorCount: 2, launcherPid: 100, editorLaunched: true },
        1
      )
    ).toBe("ready");
  });

  it("returns ready when launcher is alive and at least one editor process exists", () => {
    expect(
      evaluateEditorReadiness(
        probe({ editor_process_count: 1 }),
        { preLaunchEditorCount: 1, launcherPid: 100, editorLaunched: true },
        2
      )
    ).toBe("ready");
  });

  it("returns ready when IDE is already running and launcher exits early", () => {
    expect(
      evaluateEditorReadiness(
        probe({ launcher_pid_alive: false, editor_process_count: 1 }),
        { preLaunchEditorCount: 1, launcherPid: 100, editorLaunched: true },
        EDITOR_READINESS_EARLY_FAILURE_POLLS
      )
    ).toBe("ready");
  });

  it("returns failure when launcher exits early with no editor process", () => {
    expect(
      evaluateEditorReadiness(
        probe({ launcher_pid_alive: false, editor_process_count: 0 }),
        { preLaunchEditorCount: 0, launcherPid: 100, editorLaunched: true },
        EDITOR_READINESS_EARLY_FAILURE_POLLS
      )
    ).toBe("failure");
  });

  it("keeps waiting after the early failure window when no editor process exists", () => {
    expect(
      evaluateEditorReadiness(
        probe({ launcher_pid_alive: false, editor_process_count: 0 }),
        { preLaunchEditorCount: 0, launcherPid: 100, editorLaunched: true },
        EDITOR_READINESS_EARLY_FAILURE_POLLS + 1
      )
    ).toBe("waiting");
  });
});

describe("capturePreLaunchEditorCount", () => {
  it("passes editor through to the probe", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockResolvedValue(
      probe({ editor_process_count: 4 })
    );

    await expect(capturePreLaunchEditorCount("cursor", mockProbe)).resolves.toBe(4);
    expect(mockProbe).toHaveBeenCalledWith(null, "cursor");
  });
});

describe("startEditorReadinessProbe", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    stopEditorReadinessProbe();
    vi.useRealTimers();
  });

  it("calls onReady when count increases on poll", async () => {
    const mockProbe = vi
      .fn<ProbeEditorProcess>()
      .mockResolvedValueOnce(probe({ editor_process_count: 1 }))
      .mockResolvedValueOnce(probe({ editor_process_count: 2 }));

    const onReady = vi.fn();
    startEditorReadinessProbe({
      preLaunchEditorCount: 1,
      launcherPid: 100,
      editor: "vscode",
      editorLaunched: true,
      probe: mockProbe,
      onReady,
      onFailure: vi.fn(),
      onStillWaiting: vi.fn(),
    });

    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_POLL_MS);
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(mockProbe).toHaveBeenLastCalledWith(100, "vscode");
  });

  it("fires still waiting after 35 seconds", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockResolvedValue(
      probe({ editor_process_count: 0, launcher_pid_alive: false, launcher_pid: null })
    );
    const onStillWaiting = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 0,
      launcherPid: null,
      editor: "cursor",
      editorLaunched: true,
      probe: mockProbe,
      onReady: vi.fn(),
      onFailure: vi.fn(),
      onStillWaiting,
    });

    await vi.advanceTimersByTimeAsync(EDITOR_STILL_WAITING_MS);
    expect(onStillWaiting).toHaveBeenCalledTimes(1);
  });

  it("calls onFailure when launcher dies in the early window with no editor process", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockResolvedValue(
      probe({ launcher_pid_alive: false, editor_process_count: 0 })
    );
    const onFailure = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 1,
      launcherPid: 100,
      editor: "cursor",
      editorLaunched: true,
      probe: mockProbe,
      onReady: vi.fn(),
      onFailure,
      onStillWaiting: vi.fn(),
    });

    await vi.advanceTimersByTimeAsync(0);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it("gives up after consecutive probe-invoke failures instead of polling forever (M9)", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockRejectedValue(new Error("ipc broken"));
    const onFailure = vi.fn();
    const onReady = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 0,
      launcherPid: 100,
      editor: "cursor",
      editorLaunched: true,
      probe: mockProbe,
      onReady,
      onFailure,
      onStillWaiting: vi.fn(),
    });

    // One fewer than the cap: must still be polling, not yet given up. There's an
    // immediate first tick plus (N-2) interval ticks to reach (cap - 1) total calls.
    await vi.advanceTimersByTimeAsync(
      EDITOR_READINESS_POLL_MS * (EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES - 2)
    );
    expect(onFailure).not.toHaveBeenCalled();
    expect(mockProbe).toHaveBeenCalledTimes(EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES - 1);

    // The cap-th consecutive failure gives up.
    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_POLL_MS);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onReady).not.toHaveBeenCalled();

    // No further polling once it has given up.
    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_POLL_MS * 5);
    expect(mockProbe).toHaveBeenCalledTimes(EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES);
  });

  it("a probe success resets the consecutive-failure counter", async () => {
    const mockProbe = vi
      .fn<ProbeEditorProcess>()
      .mockRejectedValueOnce(new Error("ipc broken"))
      .mockRejectedValueOnce(new Error("ipc broken"))
      .mockResolvedValueOnce(probe({ editor_process_count: 0, launcher_pid_alive: true }))
      .mockRejectedValue(new Error("ipc broken"));
    const onFailure = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 0,
      launcherPid: 100,
      editor: "cursor",
      editorLaunched: false,
      probe: mockProbe,
      onReady: vi.fn(),
      onFailure,
      onStillWaiting: vi.fn(),
    });

    // 2 failures, 1 success, then failures again — should need a fresh run of
    // EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES failures after the reset,
    // not just reach the raw total count of failed calls.
    await vi.advanceTimersByTimeAsync(
      EDITOR_READINESS_POLL_MS * (2 + EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES - 1)
    );
    expect(onFailure).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_POLL_MS);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });

  it("gives up after the overall deadline even if every poll individually looks fine (bounded editor readiness)", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockResolvedValue(
      probe({ editor_process_count: 0, launcher_pid_alive: true })
    );
    const onFailure = vi.fn();
    const onReady = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 0,
      launcherPid: 100,
      editor: "cursor",
      editorLaunched: false,
      probe: mockProbe,
      onReady,
      onFailure,
      onStillWaiting: vi.fn(),
    });

    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_OVERALL_TIMEOUT_MS - 1);
    expect(onFailure).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onReady).not.toHaveBeenCalled();
  });

  it("the overall deadline never fires once readiness already succeeded", async () => {
    const mockProbe = vi.fn<ProbeEditorProcess>().mockResolvedValueOnce(
      probe({ editor_process_count: 5 })
    );
    const onFailure = vi.fn();
    const onReady = vi.fn();

    startEditorReadinessProbe({
      preLaunchEditorCount: 1,
      launcherPid: 100,
      editor: "cursor",
      editorLaunched: true,
      probe: mockProbe,
      onReady,
      onFailure,
      onStillWaiting: vi.fn(),
    });

    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_POLL_MS);
    expect(onReady).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(EDITOR_READINESS_OVERALL_TIMEOUT_MS);
    expect(onFailure).not.toHaveBeenCalled();
  });
});
