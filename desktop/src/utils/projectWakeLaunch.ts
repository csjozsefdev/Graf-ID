type ProjectWakePhase =
  | "idle"
  | "intro"
  | "launching"
  | "waiting_for_editor"
  | "ready_fade"
  | "failed_fade";

export interface ProjectWakeUiState {
  phase: ProjectWakePhase;
  active: boolean;
  visible: boolean;
  skipped: boolean;
  revealAllLines: boolean;
  waitingForEditor: boolean;
  loopAnimation: boolean;
}

export function createProjectWakeUiState(reducedMotion: boolean): ProjectWakeUiState {
  return {
    phase: "intro",
    active: true,
    visible: true,
    skipped: false,
    revealAllLines: reducedMotion,
    waitingForEditor: false,
    loopAnimation: false,
  };
}

export function skipProjectWakeIntro(state: ProjectWakeUiState): ProjectWakeUiState {
  return {
    ...state,
    skipped: true,
    revealAllLines: true,
  };
}

export function beginProjectWakeLaunch(state: ProjectWakeUiState): ProjectWakeUiState {
  return {
    ...state,
    phase: "launching",
    loopAnimation: true,
    revealAllLines: true,
  };
}

export function projectWakeLaunchWaiting(state: ProjectWakeUiState): ProjectWakeUiState {
  return {
    ...state,
    phase: "waiting_for_editor",
    waitingForEditor: true,
    loopAnimation: true,
    revealAllLines: true,
  };
}

export function projectWakeEditorReady(state: ProjectWakeUiState): ProjectWakeUiState {
  return {
    ...state,
    phase: "ready_fade",
    visible: false,
    waitingForEditor: false,
    loopAnimation: false,
  };
}

export function projectWakeLaunchFailed(state: ProjectWakeUiState): ProjectWakeUiState {
  return {
    ...state,
    phase: "failed_fade",
    visible: false,
    waitingForEditor: false,
    loopAnimation: false,
  };
}

