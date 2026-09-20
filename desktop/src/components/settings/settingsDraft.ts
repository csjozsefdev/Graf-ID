import type { Dispatch, SetStateAction } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import type { AppSettingsData, CodingAgentConfig } from "../../ipc/types";
import type { GrafiSettings } from "../../shared/grafi-advisor";
import { loadGrafiSettings } from "../../utils/grafiSettings";

export interface SettingsDraft {
  default_project_opener: string;
  usage_journal_enabled: boolean;
  debug_timing_enabled: boolean;
  compact_mode: boolean;
  python_interpreter_mode: string;
  python_interpreter_custom_path: string;
  custom_opener_path: string;
  grafi_enabled: boolean;
  grafi_motion_enabled: boolean;
  grafi_critical_alerts_only: boolean;
  grafi_helping_mode_enabled: boolean;
  /** Full merged list (built-ins + custom); only custom entries are editable
   * here. A not-yet-saved custom agent has id === "" until Save assigns it
   * a real, system-generated id (M9: ids are not a user-facing field). */
  codingAgents: CodingAgentConfig[];
  /** Built-in presets the user removed; restorable until/after Save. */
  removedBuiltinAgents: CodingAgentConfig[];
}

/** Local draft for the add/edit coding-agent form. Arguments are edited as
 * one-per-line text and split into a real string array on save — never
 * reassembled into a shell command, so no escaping is ever needed here. */
export type SetDraft = Dispatch<SetStateAction<SettingsDraft | null>>;

export interface AgentFormDraft {
  /** Built-in presets keep a fixed name; only executable override/args are editable. */
  builtIn: boolean;
  id: string;
  display_name: string;
  executable: string;
  argsText: string;
}

function grafiDraftFromSettings(grafi: GrafiSettings): Pick<
  SettingsDraft,
  | "grafi_enabled"
  | "grafi_motion_enabled"
  | "grafi_critical_alerts_only"
  | "grafi_helping_mode_enabled"
> {
  return {
    grafi_enabled: grafi.enabled,
    grafi_motion_enabled: grafi.motionEnabled,
    grafi_critical_alerts_only: grafi.criticalAlertsOnly,
    grafi_helping_mode_enabled: grafi.helpingModeEnabled,
  };
}

export function grafiSettingsFromDraft(draft: SettingsDraft): GrafiSettings {
  return {
    enabled: draft.grafi_enabled,
    motionEnabled: draft.grafi_motion_enabled,
    criticalAlertsOnly: draft.grafi_critical_alerts_only,
    helpingModeEnabled: draft.grafi_helping_mode_enabled,
  };
}

export function applyCompactMode(enabled: boolean) {
  document.documentElement.classList.toggle("grafid-compact", enabled);
}

export function toDraft(data: AppSettingsData): SettingsDraft {
  return {
    default_project_opener: data.default_project_opener,
    usage_journal_enabled: data.usage_journal_enabled,
    debug_timing_enabled: data.debug_timing_enabled,
    compact_mode: Boolean(data.compact_mode),
    python_interpreter_mode: data.python_interpreter_mode ?? "auto",
    python_interpreter_custom_path: data.python_interpreter_custom_path ?? "",
    custom_opener_path: data.custom_opener_path ?? "",
    codingAgents: data.coding_agents ?? [],
    removedBuiltinAgents: data.removed_builtin_agents ?? [],
    ...grafiDraftFromSettings(loadGrafiSettings()),
  };
}

export async function pickExecutable(title: string): Promise<string | null> {
  const selected = await open({
    title,
    multiple: false,
    directory: false,
  });
  if (typeof selected === "string") {
    return selected;
  }
  return null;
}
