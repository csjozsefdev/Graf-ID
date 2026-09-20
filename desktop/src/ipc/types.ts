/** IPC types mirroring Python grafid.ipc envelope (English-only). */

type GitStateKind = "unknown" | "not_repo" | "clean" | "dirty";

export type NavSection = "dashboard" | "history" | "settings";

interface OpenerOption {
  id: string;
  label: string;
}

/**
 * A Coding Agent is any interactive CLI tool launched in a project's root
 * directory (Claude Code, Codex CLI, or a user-defined tool) — deliberately
 * separate from editors: no work session, no lifecycle tracking, no Exit
 * Note. See docs/CODING_AGENTS.md.
 */
export interface CodingAgentConfig {
  id: string;
  display_name: string;
  executable: string;
  args: string[];
  built_in: boolean;
  available: boolean;
  /** Built-in presets only: user-defined explicit executable path, if any. */
  executable_override?: string | null;
  /** Built-in presets only: the PATH command detected when there is no override. */
  default_executable?: string;
  /** Why the agent is unavailable (e.g. an invalid explicit path), if known. */
  unavailable_reason?: string | null;
}

export interface AppSettingsData {
  data_dir: string;
  logs_dir: string;
  config_dir: string;
  config_path: string;
  default_project_opener: string;
  usage_journal_enabled: boolean;
  debug_timing_enabled: boolean;
  compact_mode?: boolean;
  opener_options: OpenerOption[];
  python_interpreter_mode?: string;
  python_interpreter_custom_path?: string | null;
  custom_opener_path?: string | null;
  interpreter_options?: OpenerOption[];
  python_interpreter_hint?: string | null;
  coding_agents: CodingAgentConfig[];
  /** Built-in presets the user removed; can be restored from Settings. */
  removed_builtin_agents?: CodingAgentConfig[];
}

interface IpcError {
  code: string;
  message: string;
}

export interface IpcResponse<T = Record<string, unknown>> {
  ok: boolean;
  data?: T;
  error?: IpcError;
}

interface GitStatus {
  state: GitStateKind;
  label: string;
  is_git_repo: boolean;
  is_dirty: boolean;
  branch: string | null;
}

interface SessionSummary {
  id: number;
  started_at: string;
  ended_at: string | null;
  is_active: boolean;
  status: string;
  summary: string | null;
  exit_note: string | null;
  blocker: string | null;
  next_step: string | null;
}

interface SummaryPreview {
  headline: string;
  summary_text: string;
  generated_at: string;
}

export interface WorkflowLaunchResult {
  success: boolean;
  message: string;
  editor_launched: boolean;
  /** When true, desktop opens Explorer once via Rust (registered project root). */
  explorer_opened: boolean;
  fallback_used: boolean;
  action: "editor" | "explorer";
  editor: string | null;
  session_id: number | null;
  session_started: boolean;
  /** Detached launcher PID when an editor was spawned (probe only). */
  editor_pid?: number | null;
}

export interface OpenProjectResult {
  project: DashboardProject;
  launch: WorkflowLaunchResult;
}

export interface CloseSessionResult {
  project: DashboardProject;
  resume_panel: ResumePanelData;
  message: string;
  session_closed: boolean;
  resume_warning?: string | null;
}

interface SessionTimelineEntry {
  session_id: number;
  started_at: string;
  ended_at: string | null;
  status: string;
  exit_note_preview: string | null;
  duration_label: string | null;
}

interface AttributedLine {
  text: string;
  source: string;
}

export interface RefreshContract {
  scan_ok: boolean;
  snapshot_id: number | null;
  scan_error?: string | null;
  git_ok: boolean;
  mode: string;
  snapshots_pruned?: number;
}

export interface DashboardProject {
  id: number;
  name: string;
  path: string;
  /** False when the registered folder no longer exists on disk. */
  path_accessible?: boolean;
  /** Set when dashboard preload could not build full detail for this project. */
  load_error?: string | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
  preferred_ide: string | null;
  is_active: boolean;
  has_open_session?: boolean;
  category: string;
  status: string;
  notes: string | null;
  last_refreshed_at: string | null;
  sidebar_order?: number | null;
  latest_session: SessionSummary | null;
  summary_preview: SummaryPreview | null;
  git_status: GitStatus;
  has_resume: boolean;
  open_task_count: number | null;
  latest_scan_at: string | null;
  /** Cached panel to avoid IPC on project selection. */
  resume_panel?: ResumePanelData;
  /** Cached scan history to avoid IPC on History tab open. */
  history?: HistoryRow[];
}

export interface BootstrapData {
  config_dir: string;
  config_path: string;
  database_path: string;
  schema_version: number;
  projects: DashboardProject[];
  /** Cached settings to avoid IPC on Settings open. */
  app_settings?: AppSettingsData | null;
}

export interface MvpSection {
  title: string;
  body: string;
}

/** Backend ProjectContext snapshot: only reliable facts, never scanner marker text. */
export interface ProjectSnapshot {
  current_focus?: string[];
  open_issues?: string[];
  recent_fixes?: string[];
  recent_improvements?: string[];
  suggested_next_step?: string | null;
}

interface StartupSummaryBlock {
  headline: string;
  summary_text: string;
  scroll_excerpt: string | null;
  generated_at: string;
  source?: string;
  sources_used?: string[];
  attributed_lines?: AttributedLine[];
  timeline?: SessionTimelineEntry[];
  away_label?: string | null;
  workflow_files?: string[];
  confidence?: string;
  mvp_sections?: MvpSection[];
  project_snapshot?: ProjectSnapshot | null;
}

export interface ResumePanelData {
  startup_summary: StartupSummaryBlock | null;
  blocker: string | null;
  next_step: string | null;
  exit_note: string | null;
  modified_files: string[];
  stored_resume_excerpt: string | null;
  git_status: GitStatus;
  has_stored_resume: boolean;
  latest_session: SessionSummary | null;
  last_opened_at: string | null;
  open_task_count: number | null;
  latest_scan_at: string | null;
  last_refreshed_at?: string | null;
  workflow_files?: string[];
  sources_used?: string[];
  timeline?: SessionTimelineEntry[];
  attributed_lines?: AttributedLine[];
  away_label?: string | null;
  confidence?: string;
  mvp_sections?: MvpSection[];
  project_snapshot?: ProjectSnapshot | null;
}

export interface HistoryRow {
  snapshot_id: number;
  scanned_at: string;
  project_name: string;
  scanned_at_label: string;
  summary_preview: string;
  changed_files_count: number | null;
  session_duration_label: string | null;
  findings_count: number;
  scanned_files_count: number;
  duration_seconds: number;
  git_branch: string | null;
  git_dirty: boolean | null;
  is_git_repo: boolean;
  summary_source: "session_best_effort" | "scan";
}

export interface ProjectDetailData {
  project: DashboardProject;
  resume_panel: ResumePanelData;
  /** Loaded via `project-history` when the History tab is opened. */
  history?: HistoryRow[];
}

export type AppLoadState =
  | { status: "loading" }
  | { status: "ready"; bootstrap: BootstrapData }
  | { status: "error"; title: string; message: string; code?: string };
