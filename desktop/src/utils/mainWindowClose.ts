import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

import { stopEditorReadinessProbe } from "./editorReadinessProbe";
import { isEditorLifecycleProbeActive, stopEditorLifecycleProbe } from "./editorSessionProbe";
import { hideToTray } from "./hideToTray";

export type MainWindowCloseMode = "hide_tray" | "quit";

export type MainWindowCloseContext = {
  editorLifecycleActive: boolean;
  hideToTrayUsed: boolean;
  closeSessionBusy: boolean;
};

type MainWindowCloseHandler = () => void | Promise<void>;

let customCloseHandler: MainWindowCloseHandler | null = null;
let closeRequestInFlight = false;

export function resolveMainWindowCloseMode(
  context: Pick<
    MainWindowCloseContext,
    "editorLifecycleActive" | "hideToTrayUsed"
  >
): MainWindowCloseMode {
  if (context.editorLifecycleActive || context.hideToTrayUsed) {
    return "hide_tray";
  }
  return "quit";
}

export function setMainWindowCloseHandler(handler: MainWindowCloseHandler | null) {
  customCloseHandler = handler;
}

async function quitMainWindow(): Promise<void> {
  stopEditorLifecycleProbe();
  stopEditorReadinessProbe();
  await invoke("quit_app");
}

export async function executeMainWindowClose(
  context: MainWindowCloseContext = {
    editorLifecycleActive: isEditorLifecycleProbeActive(),
    hideToTrayUsed: false,
    closeSessionBusy: false,
  }
): Promise<void> {
  if (context.closeSessionBusy) {
    return;
  }

  const mode = resolveMainWindowCloseMode(context);
  if (mode === "hide_tray") {
    await hideToTray();
    return;
  }

  await quitMainWindow();
}

/** Guarded against reentrancy — a second close request (rapid click, Alt+F4 repeat) is a no-op
 * while the first is still resolving, so overlapping calls can't race each other's side effects. */
export async function requestMainWindowClose(): Promise<void> {
  if (closeRequestInFlight) {
    return;
  }
  closeRequestInFlight = true;
  try {
    if (customCloseHandler) {
      await customCloseHandler();
      return;
    }
    await executeMainWindowClose();
  } finally {
    closeRequestInFlight = false;
  }
}

/** Intercept native close (Alt+F4) and route through the same policy as the custom button. */
export async function setupMainWindowCloseRequestListener(): Promise<() => void> {
  const appWindow = getCurrentWindow();
  return appWindow.onCloseRequested(async (event) => {
    event.preventDefault();
    await requestMainWindowClose();
  });
}
