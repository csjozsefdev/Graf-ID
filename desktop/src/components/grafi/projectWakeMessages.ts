export interface ProjectWakeTerminalLine {
  delayMs: number;
  text: string;
}

export const PROJECT_WAKE_TERMINAL_LINES: readonly ProjectWakeTerminalLine[] = [
  { delayMs: 0, text: "> Project wake sequence initiated..." },
  { delayMs: 600, text: "> Establishing workspace..." },
  { delayMs: 1200, text: "> Preparing development environment..." },
  { delayMs: 1800, text: "> Handing off to IDE..." },
] as const;

export const PROJECT_WAKE_LAUNCH_DELAY_MS = 2400;

/** Fallback cycle length when intro video metadata is unavailable. */
export const PROJECT_WAKE_VIDEO_CYCLE_FALLBACK_MS = 5000;

export const PROJECT_WAKE_SLOW_STARTUP_MESSAGE =
  "Project startup is taking longer than expected...";
