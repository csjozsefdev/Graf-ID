import { invoke } from "@tauri-apps/api/core";

export interface EditorProcessProbe {
  launcher_pid: number | null;
  launcher_pid_alive: boolean;
  editor_image: string | null;
  editor_process_count: number;
}

export type ProbeEditorProcess = (
  launcherPid: number | null,
  editor: string | null
) => Promise<EditorProcessProbe>;

export const EDITOR_READINESS_POLL_MS = 1500;
export const EDITOR_STILL_WAITING_MS = 35000;
export const EDITOR_READINESS_EARLY_FAILURE_POLLS = 3;
/** M9: if the probe invoke itself keeps throwing (a broken/missing Tauri command),
 * this many consecutive failures gives up instead of polling silently forever. */
export const EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES = 5;
/** Absolute ceiling on how long readiness polling can run, regardless of cause —
 * covers the case where probe calls keep succeeding but never report "ready" or
 * "failure" (e.g. the editor never actually opens a window). */
export const EDITOR_READINESS_OVERALL_TIMEOUT_MS = 60000;

export interface EditorReadinessProbeContext {
  preLaunchEditorCount: number;
  launcherPid: number | null;
  editor: string | null;
  editorLaunched: boolean;
  probe?: ProbeEditorProcess;
  onReady: () => void;
  onFailure: () => void;
  onStillWaiting?: () => void;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;
let stillWaitingTimer: ReturnType<typeof setTimeout> | null = null;
let overallTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
let pollSeq = 0;
let consecutiveProbeFailures = 0;
let activeReady = false;
let activeFailure = false;

const defaultProbe: ProbeEditorProcess = (launcherPid, editor) =>
  invoke<EditorProcessProbe>("probe_editor_process", {
    launcherPid,
    editor,
  });

export async function capturePreLaunchEditorCount(
  editor: string | null,
  probe: ProbeEditorProcess = defaultProbe
): Promise<number> {
  const result = await probe(null, editor);
  return result.editor_process_count;
}

export function evaluateEditorReadiness(
  probe: EditorProcessProbe,
  context: Pick<
    EditorReadinessProbeContext,
    "preLaunchEditorCount" | "launcherPid" | "editorLaunched"
  >,
  pollNumber: number
): "ready" | "failure" | "waiting" {
  const countIncreased = probe.editor_process_count > context.preLaunchEditorCount;
  if (countIncreased) {
    return "ready";
  }

  if (
    context.editorLaunched &&
    context.launcherPid !== null &&
    probe.launcher_pid_alive &&
    probe.editor_process_count >= 1
  ) {
    return "ready";
  }

  if (
    context.editorLaunched &&
    probe.editor_process_count >= 1
  ) {
    return "ready";
  }

  if (
    context.launcherPid !== null &&
    !probe.launcher_pid_alive &&
    pollNumber <= EDITOR_READINESS_EARLY_FAILURE_POLLS &&
    !countIncreased &&
    probe.editor_process_count === 0
  ) {
    return "failure";
  }

  return "waiting";
}

export function startEditorReadinessProbe(context: EditorReadinessProbeContext) {
  stopEditorReadinessProbe();
  const probeFn = context.probe ?? defaultProbe;
  pollSeq = 0;
  consecutiveProbeFailures = 0;
  activeReady = false;
  activeFailure = false;

  const finishReady = () => {
    if (activeReady || activeFailure) {
      return;
    }
    activeReady = true;
    stopEditorReadinessProbe();
    context.onReady();
  };

  const finishFailure = () => {
    if (activeReady || activeFailure) {
      return;
    }
    activeFailure = true;
    stopEditorReadinessProbe();
    context.onFailure();
  };

  if (context.onStillWaiting) {
    const onStillWaiting = context.onStillWaiting;
    stillWaitingTimer = setTimeout(() => {
      if (activeReady || activeFailure) {
        return;
      }
      onStillWaiting();
    }, EDITOR_STILL_WAITING_MS);
  }

  // Absolute ceiling — even if every poll individually looks fine (keeps returning
  // "waiting"), readiness detection must not run forever.
  overallTimeoutTimer = setTimeout(() => {
    finishFailure();
  }, EDITOR_READINESS_OVERALL_TIMEOUT_MS);

  const tick = async () => {
    if (activeReady || activeFailure) {
      return;
    }

    pollSeq += 1;
    try {
      const probe = await probeFn(context.launcherPid, context.editor);
      if (activeReady || activeFailure) {
        return;
      }
      consecutiveProbeFailures = 0;

      const outcome = evaluateEditorReadiness(
        probe,
        {
          preLaunchEditorCount: context.preLaunchEditorCount,
          launcherPid: context.launcherPid,
          editorLaunched: context.editorLaunched,
        },
        pollSeq
      );

      if (outcome === "ready") {
        finishReady();
      } else if (outcome === "failure") {
        finishFailure();
      }
    } catch {
      // M9: the probe invoke itself failed (e.g. a broken/missing Tauri command) —
      // non-fatal for a handful of ticks, but must not poll silently forever.
      consecutiveProbeFailures += 1;
      if (consecutiveProbeFailures >= EDITOR_READINESS_MAX_CONSECUTIVE_PROBE_FAILURES) {
        finishFailure();
      }
    }
  };

  void tick();
  pollTimer = setInterval(() => {
    void tick();
  }, EDITOR_READINESS_POLL_MS);
}

export function stopEditorReadinessProbe() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (stillWaitingTimer !== null) {
    clearTimeout(stillWaitingTimer);
    stillWaitingTimer = null;
  }
  if (overallTimeoutTimer !== null) {
    clearTimeout(overallTimeoutTimer);
    overallTimeoutTimer = null;
  }
  pollSeq = 0;
  consecutiveProbeFailures = 0;
}
