import {
  PROJECT_WAKE_LAUNCH_DELAY_MS,
  PROJECT_WAKE_TERMINAL_LINES,
} from "../components/grafi/projectWakeMessages";

export { PROJECT_WAKE_LAUNCH_DELAY_MS };

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function getProjectWakeLaunchDelayMs(reducedMotion = false): number {
  return reducedMotion ? 0 : PROJECT_WAKE_LAUNCH_DELAY_MS;
}

export function getVisibleTerminalLineCount(elapsedMs: number): number {
  if (elapsedMs < 0) {
    return 0;
  }
  let visible = 0;
  for (const line of PROJECT_WAKE_TERMINAL_LINES) {
    if (elapsedMs >= line.delayMs) {
      visible += 1;
    }
  }
  return visible;
}

export function getVisibleTerminalLineCountLooping(
  elapsedMs: number,
  cycleDurationMs: number = PROJECT_WAKE_LAUNCH_DELAY_MS
): number {
  if (elapsedMs < 0) {
    return 0;
  }
  const cycleElapsed =
    cycleDurationMs > 0 ? elapsedMs % cycleDurationMs : elapsedMs;
  return getVisibleTerminalLineCount(cycleElapsed);
}
