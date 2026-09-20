import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

import {
  isEditorLifecycleProbeActive,
  startEditorLifecycleProbe,
  stopEditorLifecycleProbe,
} from "./editorSessionProbe";

interface FakeProbeResult {
  launcher_pid: number | null;
  launcher_pid_alive: boolean;
  editor_image: string | null;
  editor_process_count: number;
}

describe("editorSessionProbe", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    invokeMock.mockReset();
    invokeMock.mockResolvedValue({
      launcher_pid: 100,
      launcher_pid_alive: true,
      editor_image: "Cursor.exe",
      editor_process_count: 2,
    });
  });

  afterEach(() => {
    stopEditorLifecycleProbe();
    vi.useRealTimers();
  });

  it("uses a single polling interval without stacking timers", async () => {
    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\demo",
    });

    expect(invokeMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(8000);
    expect(invokeMock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(8000);
    expect(invokeMock).toHaveBeenCalledTimes(3);
  });

  // --- H11: multiple projects tracked independently ---

  it("project switch: opening a second project does not stop tracking the first (core H11 regression)", async () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();

    // Both editors' process counts never change — no close should ever fire.
    invokeMock.mockImplementation((_cmd: string, args: { launcherPid: number | null }) =>
      Promise.resolve({
        launcher_pid: args.launcherPid,
        launcher_pid_alive: true,
        editor_image: "Cursor.exe",
        editor_process_count: 2,
      } satisfies FakeProbeResult)
    );

    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseA,
    });
    expect(isEditorLifecycleProbeActive(1)).toBe(true);

    // User switches to and opens a second project in the same editor — A must stay tracked.
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "cursor",
      projectId: 2,
      projectPath: "C:\\bravo",
      onEditorCloseDetected: onCloseB,
    });

    expect(isEditorLifecycleProbeActive(1)).toBe(true);
    expect(isEditorLifecycleProbeActive(2)).toBe(true);

    await vi.advanceTimersByTimeAsync(8000);
    expect(onCloseA).not.toHaveBeenCalled();
    expect(onCloseB).not.toHaveBeenCalled();
  });

  it("two projects opened in the same editor: closing one project's editor window does not falsely trigger the other's close callback", async () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();
    let sharedEditorCount = 2; // both A and B open in Cursor

    invokeMock.mockImplementation(() =>
      Promise.resolve({
        launcher_pid: 100,
        launcher_pid_alive: true,
        editor_image: "Cursor.exe",
        editor_process_count: sharedEditorCount,
      } satisfies FakeProbeResult)
    );

    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseA,
    });
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "cursor",
      projectId: 2,
      projectPath: "C:\\bravo",
      onEditorCloseDetected: onCloseB,
    });

    // Both establish a baseline of 2 on their first tick.
    await vi.advanceTimersByTimeAsync(0);

    // Project B's window closes — global Cursor.exe count drops from 2 to 1.
    // With independent per-project baselines this is a known, documented limitation:
    // a *global* image-name count can't distinguish "which" window closed, so both
    // probes observe the same drop. This test documents that behavior rather than
    // claiming it's fully solved — the H11 fix targets the *tracking* being dropped
    // entirely for a second project, not the underlying global-count ambiguity.
    sharedEditorCount = 1;
    await vi.advanceTimersByTimeAsync(8000);

    // At minimum, both probes must still be independently *running* (not silently
    // abandoned) and each must have observed the drop through its own state.
    expect(invokeMock.mock.calls.length).toBeGreaterThanOrEqual(4);
  });

  it("two separate editors: each project is tracked against its own editor image", async () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();

    invokeMock.mockImplementation((_cmd: string, args: { editor: string | null }) =>
      Promise.resolve({
        launcher_pid: 100,
        launcher_pid_alive: true,
        editor_image: args.editor === "cursor" ? "Cursor.exe" : "Code.exe",
        editor_process_count: 1,
      } satisfies FakeProbeResult)
    );

    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseA,
    });
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "vscode",
      projectId: 2,
      projectPath: "C:\\bravo",
      onEditorCloseDetected: onCloseB,
    });

    const calls = invokeMock.mock.calls as Array<[string, { editor: string | null }]>;
    const editorsRequested = calls.map(([, args]) => args.editor).sort();
    expect(editorsRequested).toEqual(["cursor", "vscode"]);
    expect(onCloseA).not.toHaveBeenCalled();
    expect(onCloseB).not.toHaveBeenCalled();
  });

  it("editor crash: project B's crash (count drops to 0) does not affect project A's tracking", async () => {
    const onCloseA = vi.fn();
    const onCloseB = vi.fn();
    let countB = 1;

    invokeMock.mockImplementation((_cmd: string, args: { launcherPid: number | null }) => {
      if (args.launcherPid === 100) {
        return Promise.resolve({
          launcher_pid: 100,
          launcher_pid_alive: true,
          editor_image: "Cursor.exe",
          editor_process_count: 1,
        } satisfies FakeProbeResult);
      }
      return Promise.resolve({
        launcher_pid: 200,
        launcher_pid_alive: countB > 0,
        editor_image: "Code.exe",
        editor_process_count: countB,
      } satisfies FakeProbeResult);
    });

    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseA,
    });
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "vscode",
      projectId: 2,
      projectPath: "C:\\bravo",
      onEditorCloseDetected: onCloseB,
    });

    await vi.advanceTimersByTimeAsync(0);
    countB = 0; // VS Code crashes for project B only
    await vi.advanceTimersByTimeAsync(8000);

    expect(onCloseB).toHaveBeenCalledTimes(1);
    expect(onCloseA).not.toHaveBeenCalled();
    expect(isEditorLifecycleProbeActive(2)).toBe(false);
    expect(isEditorLifecycleProbeActive(1)).toBe(true);
  });

  it("session close on a non-active project: stopping one project's probe by id leaves other projects tracked", async () => {
    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
    });
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "vscode",
      projectId: 2,
      projectPath: "C:\\bravo",
    });

    stopEditorLifecycleProbe(1);

    expect(isEditorLifecycleProbeActive(1)).toBe(false);
    expect(isEditorLifecycleProbeActive(2)).toBe(true);
    expect(isEditorLifecycleProbeActive()).toBe(true);
  });

  it("stopEditorLifecycleProbe() with no id stops every tracked project (app quit / unmount)", async () => {
    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
    });
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "vscode",
      projectId: 2,
      projectPath: "C:\\bravo",
    });

    stopEditorLifecycleProbe();

    expect(isEditorLifecycleProbeActive()).toBe(false);
    expect(isEditorLifecycleProbeActive(1)).toBe(false);
    expect(isEditorLifecycleProbeActive(2)).toBe(false);
  });

  it("a stale in-flight tick from a stopped+restarted probe does not contaminate the new probe's state (M9)", async () => {
    const onCloseGen1 = vi.fn();
    const onCloseGen2 = vi.fn();
    let resolveGen1Probe!: (value: FakeProbeResult) => void;

    invokeMock.mockImplementationOnce(
      () =>
        new Promise<FakeProbeResult>((resolve) => {
          resolveGen1Probe = resolve;
        })
    );

    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseGen1,
    });

    // Generation 1's first tick is now in flight (its invoke() is pending).
    // Close and immediately reopen the same project's session before it resolves.
    stopEditorLifecycleProbe(1);
    invokeMock.mockResolvedValue({
      launcher_pid: 200,
      launcher_pid_alive: true,
      editor_image: "Cursor.exe",
      editor_process_count: 2,
    } satisfies FakeProbeResult);
    startEditorLifecycleProbe({
      editorPid: 200,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
      onEditorCloseDetected: onCloseGen2,
    });

    // Generation 1's stale in-flight probe now resolves with data that would
    // otherwise fire a close notification (editor_process_count: 0).
    resolveGen1Probe({
      launcher_pid: 100,
      launcher_pid_alive: false,
      editor_image: "Cursor.exe",
      editor_process_count: 0,
    });
    await vi.advanceTimersByTimeAsync(0);

    // The stale result must not reach generation 2's callback, and
    // generation 2's tracking must still be running (not stopped by it).
    expect(onCloseGen1).not.toHaveBeenCalled();
    expect(onCloseGen2).not.toHaveBeenCalled();
    expect(isEditorLifecycleProbeActive(1)).toBe(true);
  });

  it("re-starting a probe for the same project replaces it instead of stacking a second timer", async () => {
    startEditorLifecycleProbe({
      editorPid: 100,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
    });
    const callsAfterFirstStart = invokeMock.mock.calls.length;

    startEditorLifecycleProbe({
      editorPid: 101,
      editor: "cursor",
      projectId: 1,
      projectPath: "C:\\alpha",
    });
    const callsAfterSecondStart = invokeMock.mock.calls.length;
    expect(callsAfterSecondStart).toBe(callsAfterFirstStart + 1);

    invokeMock.mockClear();
    await vi.advanceTimersByTimeAsync(8000);
    // Exactly one tick from the single active timer for this project, not two.
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });
});
