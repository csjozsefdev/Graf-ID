import { describe, expect, it } from "vitest";
import {
  getProjectWakeLaunchDelayMs,
  getVisibleTerminalLineCount,
  getVisibleTerminalLineCountLooping,
  PROJECT_WAKE_LAUNCH_DELAY_MS,
} from "./projectWakeTiming";

describe("getVisibleTerminalLineCount", () => {
  it("returns zero lines for negative elapsed values", () => {
    expect(getVisibleTerminalLineCount(-100)).toBe(0);
  });

  it("reveals the first line at 0 ms", () => {
    expect(getVisibleTerminalLineCount(0)).toBe(1);
  });

  it("reveals lines at each timing boundary", () => {
    expect(getVisibleTerminalLineCount(599)).toBe(1);
    expect(getVisibleTerminalLineCount(600)).toBe(2);
    expect(getVisibleTerminalLineCount(1199)).toBe(2);
    expect(getVisibleTerminalLineCount(1200)).toBe(3);
    expect(getVisibleTerminalLineCount(1799)).toBe(3);
    expect(getVisibleTerminalLineCount(1800)).toBe(4);
  });

  it("returns all lines after the final boundary", () => {
    expect(getVisibleTerminalLineCount(2400)).toBe(4);
    expect(getVisibleTerminalLineCount(99999)).toBe(4);
  });
});

describe("getProjectWakeLaunchDelayMs", () => {
  it("uses the normal launch delay constant", () => {
    expect(PROJECT_WAKE_LAUNCH_DELAY_MS).toBe(2400);
    expect(getProjectWakeLaunchDelayMs(false)).toBe(2400);
  });

  it("returns zero when reduced motion is enabled", () => {
    expect(getProjectWakeLaunchDelayMs(true)).toBe(0);
  });
});

describe("getVisibleTerminalLineCountLooping", () => {
  it("restarts the terminal sequence each cycle", () => {
    expect(getVisibleTerminalLineCountLooping(2400)).toBe(1);
    expect(getVisibleTerminalLineCountLooping(2999)).toBe(1);
    expect(getVisibleTerminalLineCountLooping(3000)).toBe(2);
  });
});
