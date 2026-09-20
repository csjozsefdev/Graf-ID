import { describe, expect, it } from "vitest";
import { EDITOR_STILL_WAITING_MS } from "./editorReadinessProbe";
import {
  beginProjectWakeLaunch,
  createProjectWakeUiState,
  projectWakeEditorReady,
  projectWakeLaunchFailed,
  projectWakeLaunchWaiting,
  skipProjectWakeIntro,
} from "./projectWakeLaunch";

describe("projectWakeLaunch", () => {
  it("starts in intro with overlay visible", () => {
    const state = createProjectWakeUiState(false);
    expect(state.phase).toBe("intro");
    expect(state.active).toBe(true);
    expect(state.visible).toBe(true);
    expect(state.waitingForEditor).toBe(false);
  });

  it("moves through launch and waiting phases", () => {
    let state = createProjectWakeUiState(false);
    state = beginProjectWakeLaunch(state);
    expect(state.phase).toBe("launching");
    expect(state.loopAnimation).toBe(true);
    expect(state.revealAllLines).toBe(true);

    state = projectWakeLaunchWaiting(state);
    expect(state.phase).toBe("waiting_for_editor");
    expect(state.loopAnimation).toBe(true);
    expect(state.waitingForEditor).toBe(true);
  });

  it("fades out on ready and failed paths", () => {
    const waiting = projectWakeLaunchWaiting(createProjectWakeUiState(false));
    expect(projectWakeEditorReady(waiting)).toMatchObject({
      phase: "ready_fade",
      visible: false,
    });
    expect(projectWakeLaunchFailed(waiting)).toMatchObject({
      phase: "failed_fade",
      visible: false,
    });
  });

  it("reveals all lines when intro is skipped", () => {
    const skipped = skipProjectWakeIntro(createProjectWakeUiState(false));
    expect(skipped.skipped).toBe(true);
    expect(skipped.revealAllLines).toBe(true);
  });

  it("uses the 35 second still-waiting threshold constant", () => {
    expect(EDITOR_STILL_WAITING_MS).toBe(35000);
  });
});