import { invoke } from "@tauri-apps/api/core";

interface EditorProcessProbe {
  launcher_pid: number | null;
  launcher_pid_alive: boolean;
  editor_image: string | null;
  editor_process_count: number;
}

export interface EditorProbeContext {
  editorPid: number | null;
  editor: string | null;
  projectId: number;
  projectPath: string;
  onEditorCloseDetected?: () => void;
}

interface ProbeState {
  timer: ReturnType<typeof setInterval>;
  seq: number;
  baselineEditorCount: number | null;
  launcherExitedEarly: boolean;
  closeNotified: boolean;
  onEditorCloseDetected?: () => void;
}

/**
 * One probe per project (H11) — a module-level singleton here previously meant
 * opening a second project silently dropped lifecycle tracking of the first
 * (its editor could close without ever showing the exit-note dialog). Keyed by
 * projectId so each project's own baseline/state is independent.
 */
const probes = new Map<number, ProbeState>();

/** True when any project's editor lifecycle is being tracked, or (with an id) one specific project's. */
export function isEditorLifecycleProbeActive(projectId?: number): boolean {
  if (projectId === undefined) {
    return probes.size > 0;
  }
  return probes.has(projectId);
}

function clearProbeState(projectId: number): void {
  const state = probes.get(projectId);
  if (state) {
    clearInterval(state.timer);
    probes.delete(projectId);
  }
}

/** Stop tracking one project's editor lifecycle, or every project's if no id is given. */
export function stopEditorLifecycleProbe(projectId?: number): void {
  if (projectId === undefined) {
    for (const id of [...probes.keys()]) {
      clearProbeState(id);
    }
    return;
  }
  clearProbeState(projectId);
}

function notifyEditorCloseDetected(projectId: number): void {
  const state = probes.get(projectId);
  if (!state || state.closeNotified) {
    return;
  }
  state.closeNotified = true;
  const handler = state.onEditorCloseDetected;
  stopEditorLifecycleProbe(projectId);
  handler?.();
}

export function startEditorLifecycleProbe(context: EditorProbeContext): void {
  const projectId = context.projectId;
  // Replace any existing probe for this exact project (idempotent re-start);
  // probes for other projects are left running.
  stopEditorLifecycleProbe(projectId);

  // M9 (found during re-audit): the `ProbeState` object itself is captured
  // here, not just looked up by projectId, so a tick can tell "my probe was
  // stopped and a NEW one started for this same project while my invoke()
  // was in flight" apart from "my probe is still the live one" — both cases
  // pass a key-existence check (the new state also starts with
  // closeNotified: false), but only reference equality against `state`
  // catches the former. Without this, closing and immediately reopening a
  // session for the same project inside one 8s tick's in-flight probe call
  // let stale generation-1 data (baselineEditorCount, a close notification)
  // land on generation-2's freshly-started tracking.
  const state: ProbeState = {
    timer: undefined as unknown as ReturnType<typeof setInterval>,
    seq: 0,
    baselineEditorCount: null,
    launcherExitedEarly: false,
    closeNotified: false,
    onEditorCloseDetected: context.onEditorCloseDetected,
  };

  const tick = async () => {
    if (probes.get(projectId) !== state || state.closeNotified) {
      return;
    }

    state.seq += 1;
    try {
      const probe = await invoke<EditorProcessProbe>("probe_editor_process", {
        launcherPid: context.editorPid,
        editor: context.editor,
      });

      if (probes.get(projectId) !== state || state.closeNotified) {
        return;
      }

      if (state.baselineEditorCount === null) {
        state.baselineEditorCount = probe.editor_process_count;
      }

      if (
        context.editorPid !== null &&
        !probe.launcher_pid_alive &&
        state.seq <= 3 &&
        !state.launcherExitedEarly
      ) {
        state.launcherExitedEarly = true;
      }

      const editorCountDropped =
        state.baselineEditorCount !== null &&
        probe.editor_process_count < state.baselineEditorCount;
      const noEditorProcesses = probe.editor_process_count === 0;

      if (noEditorProcesses || (state.launcherExitedEarly && editorCountDropped)) {
        notifyEditorCloseDetected(projectId);
      }
    } catch {
      // Probe failures are non-fatal; polling continues on the next tick. Unlike the
      // readiness probe (M9), there is no bounded "give up" case here by design — a
      // lifecycle probe is expected to keep trying for as long as the session appears
      // open, since giving up would itself mean silently losing session tracking.
    }
  };

  state.timer = setInterval(() => {
    void tick();
  }, 8000);

  probes.set(projectId, state);

  void tick();
}
