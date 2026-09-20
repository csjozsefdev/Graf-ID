import { describe, expect, it } from "vitest";
import type { AppSettingsData } from "../../ipc/types";
import { DEFAULT_GRAFI_SETTINGS } from "../../utils/grafiSettings";
import { grafiSettingsFromDraft, toDraft } from "./settingsDraft";

const data = {
  default_project_opener: "agent:claude-code",
  usage_journal_enabled: true,
  debug_timing_enabled: false,
  compact_mode: true,
  python_interpreter_mode: undefined,
  python_interpreter_custom_path: undefined,
  custom_opener_path: undefined,
  coding_agents: undefined,
  removed_builtin_agents: undefined,
} as unknown as AppSettingsData;

describe("settings draft mapping", () => {
  it("fills defaults for optional backend fields", () => {
    const draft = toDraft(data);
    expect(draft.python_interpreter_mode).toBe("auto");
    expect(draft.python_interpreter_custom_path).toBe("");
    expect(draft.custom_opener_path).toBe("");
    expect(draft.codingAgents).toEqual([]);
    expect(draft.removedBuiltinAgents).toEqual([]);
    expect(draft.default_project_opener).toBe("agent:claude-code");
    expect(draft.compact_mode).toBe(true);
  });

  it("round-trips the browser-side Grafi settings", () => {
    expect(grafiSettingsFromDraft(toDraft(data))).toEqual(DEFAULT_GRAFI_SETTINGS);
  });
});
