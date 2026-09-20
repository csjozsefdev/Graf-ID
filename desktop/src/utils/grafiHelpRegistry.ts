/** Deterministic UI help topics for Grafi Helping Mode (Graf-Id layer). */

export const GRAFI_HELP_TOPIC = {
  OPEN_PROJECT: "open-project",
  REFRESH_CONTEXT: "refresh-context",
  EXPORT: "export",
  HISTORY: "history",
  SETTINGS: "settings",
  DASHBOARD: "dashboard",
  PROJECT_SELECT: "project-select",
  RESUME_SUMMARY: "resume-summary",
  EXIT_NOTE: "exit-note",
  MODIFIED_FILES: "modified-files",
  PROJECT_SEARCH: "project-search",
  PROJECT_FILTER: "project-filter",
  ADD_PROJECT: "add-project",
  SETTINGS_PYTHON_BACKEND: "settings-python-backend",
  SETTINGS_PYTHON_CUSTOM_PATH: "settings-python-custom-path",
  SETTINGS_PROJECT_OPENER: "settings-project-opener",
  SETTINGS_CUSTOM_OPENER_PATH: "settings-custom-opener-path",
  SETTINGS_USAGE_JOURNAL: "settings-usage-journal",
  SETTINGS_DEBUG_TIMING: "settings-debug-timing",
  SETTINGS_COMPACT_MODE: "settings-compact-mode",
  SETTINGS_GRAFI_ENABLED: "settings-grafi-enabled",
  SETTINGS_HELPING_MODE: "settings-helping-mode",
  SETTINGS_GRAFI_MOTION: "settings-grafi-motion",
  SETTINGS_GRAFI_CRITICAL_ONLY: "settings-grafi-critical-only",
  SETTINGS_SAVE: "settings-save",
  SETTINGS_RESET: "settings-reset",
  SETTINGS_OPEN_DATA_FOLDER: "settings-open-data-folder",
  SETTINGS_OPEN_LOGS_FOLDER: "settings-open-logs-folder",
  SETTINGS_RETRY: "settings-retry",
  SETTINGS_CODING_AGENTS: "settings-coding-agents",
} as const;

export type GrafiHelpTopic = (typeof GRAFI_HELP_TOPIC)[keyof typeof GRAFI_HELP_TOPIC];

export const GRAFI_HELP_MESSAGES: Record<GrafiHelpTopic, string> = {
  [GRAFI_HELP_TOPIC.OPEN_PROJECT]:
    "Open Project starts your editor from this saved project path, so you can continue where you left off.",
  [GRAFI_HELP_TOPIC.REFRESH_CONTEXT]:
    "Refresh scans the project again and updates the summary, files, and recent signals.",
  [GRAFI_HELP_TOPIC.EXPORT]:
    "Export saves this project context into a file you can use later or share with another tool.",
  [GRAFI_HELP_TOPIC.HISTORY]:
    "History shows older project context snapshots so you can look back at previous work.",
  [GRAFI_HELP_TOPIC.SETTINGS]:
    "Settings lets you control Grafi, motion, silence, and helper behavior.",
  [GRAFI_HELP_TOPIC.DASHBOARD]:
    "Dashboard is your home view for the selected project summary and actions.",
  [GRAFI_HELP_TOPIC.PROJECT_SELECT]:
    "Pick a project here to load its saved context, scans, and session notes.",
  [GRAFI_HELP_TOPIC.RESUME_SUMMARY]:
    "This summary shows where you left off, what changed, and what to do next.",
  [GRAFI_HELP_TOPIC.EXIT_NOTE]:
    "Exit Note is a short note for your next session: what changed, what blocked you, and what comes next.",
  [GRAFI_HELP_TOPIC.MODIFIED_FILES]:
    "Modified files lists paths that changed in the latest scan so you can spot recent work quickly.",
  [GRAFI_HELP_TOPIC.PROJECT_SEARCH]:
    "Search filters the project list by name or folder path when you have many projects.",
  [GRAFI_HELP_TOPIC.PROJECT_FILTER]:
    "Status filter narrows the sidebar to projects in a specific workflow state.",
  [GRAFI_HELP_TOPIC.ADD_PROJECT]:
    "Add project registers a folder so Graf-Id can track sessions, scans, and resume context.",
  [GRAFI_HELP_TOPIC.SETTINGS_PYTHON_BACKEND]:
    "Choose which Python runs Graf-Id commands in development. Release builds use the bundled runtime.",
  [GRAFI_HELP_TOPIC.SETTINGS_PYTHON_CUSTOM_PATH]:
    "Point to a specific python.exe when the backend preset is set to Custom Path.",
  [GRAFI_HELP_TOPIC.SETTINGS_PROJECT_OPENER]:
    "Default editor for Open Project when a project has no per-project opener set.",
  [GRAFI_HELP_TOPIC.SETTINGS_CUSTOM_OPENER_PATH]:
    "Executable path for a custom editor when Open projects with is set to Custom Path.",
  [GRAFI_HELP_TOPIC.SETTINGS_USAGE_JOURNAL]:
    "Stores local usage events on this machine only. No network telemetry is sent.",
  [GRAFI_HELP_TOPIC.SETTINGS_DEBUG_TIMING]:
    "Adds timing fields to IPC responses for troubleshooting slow backend calls.",
  [GRAFI_HELP_TOPIC.SETTINGS_COMPACT_MODE]:
    "Tightens dashboard spacing for smaller screens or dense project lists.",
  [GRAFI_HELP_TOPIC.SETTINGS_GRAFI_ENABLED]:
    "Shows or hides the Grafi advisor in the bottom-left corner of the app.",
  [GRAFI_HELP_TOPIC.SETTINGS_HELPING_MODE]:
    "Shows short tips on hover and keyboard focus for supported controls.",
  [GRAFI_HELP_TOPIC.SETTINGS_GRAFI_MOTION]:
    "Enables subtle Grafi motion when your system allows animations.",
  [GRAFI_HELP_TOPIC.SETTINGS_GRAFI_CRITICAL_ONLY]:
    "Hides non-critical Grafi messages and help tips; critical warnings still appear.",
  [GRAFI_HELP_TOPIC.SETTINGS_SAVE]:
    "Writes the current preferences to config.json in your Graf-Id data folder.",
  [GRAFI_HELP_TOPIC.SETTINGS_RESET]:
    "Restores Graf-Id and Grafi settings to their default values.",
  [GRAFI_HELP_TOPIC.SETTINGS_OPEN_DATA_FOLDER]:
    "Opens the folder that stores config.json and the local SQLite database.",
  [GRAFI_HELP_TOPIC.SETTINGS_OPEN_LOGS_FOLDER]:
    "Opens the folder with desktop-backend.log and other local log files.",
  [GRAFI_HELP_TOPIC.SETTINGS_RETRY]:
    "Reloads settings from the backend after a load or save error.",
  [GRAFI_HELP_TOPIC.SETTINGS_CODING_AGENTS]:
    "Coding agents open in the project directory and manage their own session context. Graf-Id Exit Notes are not used.",
};

export function getGrafiHelpMessage(topic: string | null | undefined): string | null {
  if (!topic) {
    return null;
  }
  return GRAFI_HELP_MESSAGES[topic as GrafiHelpTopic] ?? null;
}

export function grafiHelpTooltipId(topic: string): string {
  return `grafi-help-tooltip-${topic}`;
}

export function grafiHelpProps(topic: GrafiHelpTopic): { "data-grafi-help": GrafiHelpTopic } {
  return { "data-grafi-help": topic };
}
