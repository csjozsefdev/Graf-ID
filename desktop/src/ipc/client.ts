/**
 * Frontend IPC client — Tauri commands only (no direct DB or Python imports).
 *
 * Open Folder — "show the directory"
 * - Use openProjectFolderPath(path) → Tauri open_project_folder (Rust explorer).
 * - No Python IPC, no workflow state, opens the registered project root exactly.
 *
 * Open Project — "resume the workflow"
 * - Use openProjectWorkflow(projectId) → Python ipc open-project.
 * - Updates last_opened_at and session; may launch editor.
 * - When launch.explorer_opened is true, call openProjectFolderPath once (deduped Explorer).
 *
 * CLI: graf-id ipc open-folder / graf-id open (Python may open Explorer in-process).
 */

import { invoke } from "@tauri-apps/api/core";
import { formatUserError } from "./errors";
import { normalizeOpenProjectResult } from "./launchNormalize";
import { mergeDashboardProject } from "../utils/projectMerge";
import type {
  AppSettingsData,
  BootstrapData,
  CodingAgentConfig,
  DashboardProject,
  IpcResponse,
  OpenProjectResult,
  CloseSessionResult,
  ProjectDetailData,
  HistoryRow,
  RefreshContract,
  ResumePanelData,
} from "./types";

/** In-memory bootstrap payload (one Python subprocess per app session). */
let bootstrapCache: BootstrapData | null = null;

function debugTimingEnabled(): boolean {
  return bootstrapCache?.app_settings?.debug_timing_enabled === true;
}

function traceUi(action: string, detail: Record<string, unknown>): void {
  if (!debugTimingEnabled()) {
    return;
  }
  console.debug(`[grafid-ui] ${action}`, detail);
}

async function invokeIpc<T>(
  action: string,
  command: string,
  args?: Record<string, unknown>
): Promise<T> {
  const started = performance.now();
  traceUi(action, { phase: "start", invoke: command, spawned_python: true });
  try {
    const result = (await invoke(command, args)) as T;
    traceUi(action, {
      phase: "end",
      invoke: command,
      spawned_python: true,
      elapsed_ms: Math.round(performance.now() - started),
    });
    return result;
  } catch (err) {
    traceUi(action, {
      phase: "error",
      invoke: command,
      spawned_python: true,
      elapsed_ms: Math.round(performance.now() - started),
    });
    throw err;
  }
}

function assertOk<T>(response: IpcResponse<T>): T {
  if (!response.ok || response.data === undefined) {
    const message = response.error?.message ?? "Backend request failed";
    const code = response.error?.code ?? "ipc_error";
    const err = new Error(`${code}: ${message}`);
    throw err;
  }
  return response.data;
}

/** User-facing message from a thrown IPC/client error. */
export function getUserErrorMessage(err: unknown): string {
  return formatUserError(err);
}

export async function fetchAppSettings(): Promise<AppSettingsData> {
  const started = performance.now();
  const bootstrap = await fetchBootstrap();
  const cached = bootstrap.app_settings;
  if (cached) {
    traceUi("settings.open", {
      phase: "end",
      spawned_python: false,
      source: "bootstrap_cache",
      elapsed_ms: Math.round(performance.now() - started),
    });
    return cached;
  }
  // Fallback for older backends; should not happen in the packaged app.
  const raw = await invokeIpc<IpcResponse<AppSettingsData>>(
    "settings.open",
    "ipc_app_settings"
  );
  return assertOk(raw);
}

export interface SaveAppSettingsResult extends AppSettingsData {
  message: string;
}

export async function saveAppSettings(input: {
  default_project_opener: string;
  usage_journal_enabled: boolean;
  debug_timing_enabled: boolean;
  compact_mode?: boolean;
  python_interpreter_mode?: string;
  python_interpreter_custom_path?: string | null;
  custom_opener_path?: string | null;
  coding_agents?: CodingAgentConfig[];
  /** Built-in presets the user removed (hidden); omitted presets stay visible. */
  removed_builtin_agents?: CodingAgentConfig[];
}): Promise<SaveAppSettingsResult> {
  const raw = await invoke<IpcResponse<SaveAppSettingsResult>>("ipc_save_app_settings", {
    opener: input.default_project_opener,
    usageJournal: input.usage_journal_enabled,
    debugTiming: input.debug_timing_enabled,
    compactMode: input.compact_mode ?? false,
    pythonInterpreterMode: input.python_interpreter_mode ?? "auto",
    pythonInterpreterCustomPath: input.python_interpreter_custom_path ?? null,
    customOpenerPath: input.custom_opener_path ?? null,
    codingAgents:
      input.coding_agents !== undefined
        ? JSON.stringify(
            input.coding_agents
              .filter((a) => !a.built_in)
              .map((a) => ({
                id: a.id,
                display_name: a.display_name,
                executable: a.executable,
                args: a.args,
              }))
          )
        : null,
    builtinAgents:
      input.coding_agents !== undefined
        ? JSON.stringify(buildBuiltinAgentSettings(input.coding_agents, input.removed_builtin_agents ?? []))
        : null,
  });
  return assertOk(raw);
}

/** Per-preset state sent to the backend: an optional executable override
 * (and args) for visible built-ins, `hidden: true` for removed ones. */
function buildBuiltinAgentSettings(
  visible: CodingAgentConfig[],
  removed: CodingAgentConfig[]
): Record<string, { hidden?: boolean; executable?: string | null; args?: string[] }> {
  const result: Record<string, { hidden?: boolean; executable?: string | null; args?: string[] }> = {};
  for (const agent of visible) {
    if (!agent.built_in) continue;
    result[agent.id] = {
      executable: agent.executable_override?.trim() || null,
      args: agent.args,
    };
  }
  for (const agent of removed) {
    result[agent.id] = { hidden: true };
  }
  return result;
}

export async function resetAppSettings(): Promise<SaveAppSettingsResult> {
  const raw = await invoke<IpcResponse<SaveAppSettingsResult>>("ipc_reset_app_settings");
  return assertOk(raw);
}

export async function fetchBootstrap(): Promise<BootstrapData> {
  if (bootstrapCache) {
    traceUi("bootstrap", {
      phase: "end",
      spawned_python: false,
      source: "memory_cache",
      elapsed_ms: 0,
    });
    return bootstrapCache;
  }
  const raw = await invokeIpc<IpcResponse<BootstrapData>>("bootstrap", "ipc_bootstrap");
  const data = assertOk(raw);
  bootstrapCache = data;
  return data;
}

export interface AddProjectResult {
  project: DashboardProject;
  message: string;
}

export async function addProject(
  name: string,
  path: string,
  category?: string
): Promise<AddProjectResult> {
  const raw = await invoke<IpcResponse<AddProjectResult>>("ipc_add_project", {
    name,
    path,
    category: category ?? null,
  });
  const result = assertOk(raw);
  if (bootstrapCache && !bootstrapCache.projects.some((p) => p.id === result.project.id)) {
    bootstrapCache = {
      ...bootstrapCache,
      projects: [...bootstrapCache.projects, result.project],
    };
  }
  return result;
}

export interface RemoveProjectResult {
  project_id: number;
  project_name: string;
  message: string;
}

export async function removeProject(projectId: number): Promise<RemoveProjectResult> {
  const raw = await invoke<IpcResponse<RemoveProjectResult>>("ipc_remove_project", {
    projectId,
  });
  const result = assertOk(raw);
  if (bootstrapCache) {
    bootstrapCache = {
      ...bootstrapCache,
      projects: bootstrapCache.projects.filter((p) => p.id !== projectId),
    };
  }
  return result;
}

export interface ReorderProjectsResult {
  projects: DashboardProject[];
  message: string;
}

export async function reorderProjects(projectIds: number[]): Promise<ReorderProjectsResult> {
  const raw = await invoke<IpcResponse<ReorderProjectsResult>>("ipc_reorder_projects", {
    projectIds,
  });
  const result = assertOk(raw);
  if (bootstrapCache) {
    bootstrapCache = {
      ...bootstrapCache,
      projects: result.projects,
    };
  }
  return result;
}

export interface RefreshResumeResult extends Pick<ProjectDetailData, "project" | "resume_panel"> {
  refresh?: RefreshContract;
  last_refreshed_at?: string;
}

/** Replace one project in the bootstrap cache without mutating the array/object in place. */
function replaceBootstrapProject(
  projectId: number,
  next: (prev: DashboardProject) => DashboardProject
): void {
  if (!bootstrapCache) {
    return;
  }
  const idx = bootstrapCache.projects.findIndex((p) => p.id === projectId);
  if (idx < 0) {
    return;
  }
  const projects = bootstrapCache.projects.slice();
  projects[idx] = next(projects[idx]);
  bootstrapCache = { ...bootstrapCache, projects };
}

/** Merge a full DashboardProject-shaped patch via the null-safe merge helper. */
function mergeBootstrapProject(
  projectId: number,
  patch: DashboardProject & { resume_panel?: ResumePanelData; history?: HistoryRow[] }
): void {
  replaceBootstrapProject(projectId, (prev) => mergeDashboardProject(prev, patch));
}

/** Patch only the cached history for one project (no full DashboardProject available). */
function patchBootstrapProjectHistory(projectId: number, history: HistoryRow[]): void {
  replaceBootstrapProject(projectId, (prev) => ({ ...prev, history }));
}

export async function refreshProjectResume(
  projectId: number,
  options?: { gitOnly?: boolean }
): Promise<RefreshResumeResult> {
  const raw = await invokeIpc<IpcResponse<RefreshResumeResult>>(
    "refresh.context",
    "ipc_refresh_resume",
    {
      projectId,
      gitOnly: options?.gitOnly ?? false,
    }
  );
  const data = assertOk(raw);
  mergeBootstrapProject(projectId, {
    ...data.project,
    resume_panel: data.resume_panel,
  });
  return data;
}

export async function fetchProjectDetail(
  projectId: number
): Promise<ProjectDetailData> {
  const started = performance.now();
  const bootstrap = await fetchBootstrap();
  const project = bootstrap.projects.find((p) => p.id === projectId) ?? null;
  const panel = project?.resume_panel ?? null;
  const history = project?.history ?? [];
  if (project && panel) {
    traceUi("project.select", {
      phase: "end",
      spawned_python: false,
      source: "bootstrap_cache",
      project_id: projectId,
      elapsed_ms: Math.round(performance.now() - started),
    });
    return { project, resume_panel: panel, history };
  }
  // Fallback for older backends; should not happen in the packaged app.
  const raw = await invokeIpc<IpcResponse<ProjectDetailData>>(
    "project.select",
    "ipc_project_detail",
    { projectId }
  );
  return assertOk(raw);
}

export async function fetchProjectHistory(
  projectId: number,
  options?: { force?: boolean }
): Promise<HistoryRow[]> {
  if (!options?.force) {
    const bootstrap = await fetchBootstrap();
    const project = bootstrap.projects.find((p) => p.id === projectId) ?? null;
    if (project?.history) {
      return project.history;
    }
  }
  const raw = await invoke<IpcResponse<{ history: HistoryRow[] }>>("ipc_project_history", {
    projectId,
  });
  const history = assertOk(raw).history;
  patchBootstrapProjectHistory(projectId, history);
  return history;
}

/** Open Project: Python IPC for session, editor, and launch metadata. */
export async function openProjectWorkflow(
  projectId: number
): Promise<OpenProjectResult> {
  const raw = await invokeIpc<IpcResponse<Record<string, unknown>>>(
    "open.project",
    "ipc_open_project",
    { projectId }
  );
  try {
    const result = normalizeOpenProjectResult(assertOk(raw));
    mergeBootstrapProject(projectId, result.project);
    return result;
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    if (detail.startsWith("launch_failed:")) {
      throw err;
    }
    throw new Error(`launch_failed: ${detail}`);
  }
}

/**
 * Coding Agent launch — deliberately NOT part of openProjectWorkflow.
 *
 * Resolves an agent + project into {executable, args, cwd} (Python, PATH
 * lookup only — read-only, no session/DB writes), then hands that straight
 * to a Rust-only terminal spawn. Graf-Id never tracks the resulting
 * process: no session is created, no lifecycle probe starts, no Exit Note
 * follows. See docs/CODING_AGENTS.md.
 */
export interface CodingAgentLaunchSpec {
  executable: string;
  args: string[];
  cwd: string;
  display_name: string;
}

async function resolveCodingAgentLaunch(
  agentId: string,
  projectId: number
): Promise<CodingAgentLaunchSpec> {
  const raw = await invoke<IpcResponse<CodingAgentLaunchSpec>>(
    "ipc_resolve_coding_agent_launch",
    { agentId, projectId }
  );
  return assertOk(raw);
}

/** Rust-only: opens a visible terminal and runs the resolved command in it. */
async function launchCodingAgent(spec: CodingAgentLaunchSpec): Promise<void> {
  await invoke("launch_coding_agent", {
    cwd: spec.cwd,
    executable: spec.executable,
    args: spec.args,
  });
}

/** Resolve + launch a coding agent for a project in one call. */
export async function openProjectWithCodingAgent(
  agentId: string,
  projectId: number
): Promise<CodingAgentLaunchSpec> {
  const spec = await resolveCodingAgentLaunch(agentId, projectId);
  await launchCodingAgent(spec);
  return spec;
}

export interface CloseSessionInput {
  exit_note?: string | null;
  blocker?: string | null;
  next_step?: string | null;
  skip_notes?: boolean;
  unfinished?: string | null;
}

/** End the active work session and optionally save exit notes (existing close-session IPC). */
export async function closeProjectSession(
  projectId: number,
  input: CloseSessionInput = {}
): Promise<CloseSessionResult> {
  const raw = await invoke<IpcResponse<CloseSessionResult>>("ipc_close_session", {
    projectId,
    exitNote: input.exit_note?.trim() || null,
    blocker: input.blocker?.trim() || null,
    nextStep: input.next_step?.trim() || null,
    unfinished: input.unfinished?.trim() || null,
    skipNotes: Boolean(input.skip_notes),
  });
  const result = assertOk(raw);
  mergeBootstrapProject(projectId, result.project);
  return result;
}

/**
 * Open Folder: Rust-only Explorer for the registered project root path.
 * The desktop Open Folder button never goes through Python IPC.
 */
export async function openProjectFolderPath(path: string): Promise<void> {
  await invoke("open_project_folder", { path });
}

/** handoff = lean GrafiTalk-compatible JSON; json = full context (adds the graf_id block). */
export type ExportFormat = "handoff" | "json" | "markdown" | "txt";

export interface ExportSuggestedFilenameResult {
  project_id: number;
  format: string;
  suggested_filename: string;
}

export interface ExportProjectResult {
  project_id: number;
  path: string;
  format: string;
  bytes_written: number;
  suggested_filename: string;
}

export async function fetchExportSuggestedFilename(
  projectId: number,
  format: ExportFormat
): Promise<ExportSuggestedFilenameResult> {
  const raw = await invokeIpc<IpcResponse<ExportSuggestedFilenameResult>>(
    "export.suggest",
    "ipc_export_project_summary",
    { projectId, exportFormat: format }
  );
  return assertOk(raw);
}

export async function exportProjectSummary(
  projectId: number,
  format: ExportFormat,
  outputPath: string
): Promise<ExportProjectResult> {
  const raw = await invokeIpc<IpcResponse<ExportProjectResult>>(
    "export.write",
    "ipc_export_project_summary",
    { projectId, exportFormat: format, outputPath }
  );
  return assertOk(raw);
}

export interface BackupResult {
  path: string;
  bytes_written: number;
  message: string;
}

/** Write a consistent backup zip of the local database to `outputPath`. */
export async function createBackup(
  outputPath: string,
  includeSettings = false
): Promise<BackupResult> {
  const raw = await invokeIpc<IpcResponse<BackupResult>>("backup.create", "ipc_create_backup", {
    outputPath,
    includeSettings,
  });
  return assertOk(raw);
}

export interface RestoreBackupResult {
  project_count: number;
  pre_restore_backup: string | null;
  settings_restored: string[];
  message: string;
}

/** Restore the database from a backup zip (a safety copy of the current one is kept). */
export async function restoreBackup(
  backupPath: string,
  restoreSettings = false
): Promise<RestoreBackupResult> {
  const raw = await invokeIpc<IpcResponse<RestoreBackupResult>>(
    "backup.restore",
    "ipc_restore_backup",
    { backupPath, restoreSettings }
  );
  bootstrapCache = null;
  return assertOk(raw);
}

export interface GrafiTalkInboxResult {
  folder: string;
  project_count: number;
  message: string;
}

/** Export every project's GrafiTalk handoff file into `outputDir`. */
export async function exportGrafiTalkInbox(outputDir: string): Promise<GrafiTalkInboxResult> {
  const raw = await invokeIpc<IpcResponse<GrafiTalkInboxResult>>(
    "grafitalk.inbox",
    "ipc_export_grafitalk_inbox",
    { outputDir }
  );
  return assertOk(raw);
}

export type ContextImportMode = "append" | "replace";

export interface ContextImportPreview {
  project_id: number;
  project_name: string;
  handoff_project_name: string;
  name_matches: boolean;
  current_notes: string | null;
  /** The text that would be stored. */
  block: string;
  proposed_notes_append: string;
  /** Digest of the notes the preview saw; apply is refused if they changed. */
  fingerprint: string;
  warnings: string[];
  ignored_keys: string[];
  fits: boolean;
  files_not_imported: number;
}

/** Validate a handoff file and describe what importing it would store. Writes nothing. */
export async function previewContextImport(
  projectId: number,
  filePath: string
): Promise<ContextImportPreview> {
  const raw = await invokeIpc<IpcResponse<ContextImportPreview>>(
    "context.import.preview",
    "ipc_preview_context_import",
    { projectId, filePath }
  );
  return assertOk(raw);
}

export interface ContextImportResult {
  project_id: number;
  notes: string;
  message: string;
}

/** Store a previewed handoff in the project notes. `confirmed` must be true. */
export async function applyContextImport(
  projectId: number,
  filePath: string,
  mode: ContextImportMode,
  fingerprint: string,
  confirmed: boolean
): Promise<ContextImportResult> {
  const raw = await invokeIpc<IpcResponse<ContextImportResult>>(
    "context.import.apply",
    "ipc_apply_context_import",
    { projectId, filePath, mode, fingerprint, confirmed }
  );
  return assertOk(raw);
}

export interface DetectedBuildCache {
  kind: string;
  manifest_path: string;
  target_path: string;
  size_bytes: number;
}

export interface DetectBuildCachesResult {
  caches: DetectedBuildCache[];
}

export interface CleanBuildCacheResult {
  cache: DetectedBuildCache;
}

export async function detectBuildCaches(
  projectId: number
): Promise<DetectBuildCachesResult> {
  const raw = await invokeIpc<IpcResponse<DetectBuildCachesResult>>(
    "build_cache.detect",
    "ipc_detect_build_caches",
    { projectId }
  );
  return assertOk(raw);
}

export async function cleanBuildCache(
  projectId: number,
  manifestPath: string
): Promise<CleanBuildCacheResult> {
  const raw = await invokeIpc<IpcResponse<CleanBuildCacheResult>>(
    "build_cache.clean",
    "ipc_clean_build_cache",
    { projectId, manifestPath }
  );
  return assertOk(raw);
}
