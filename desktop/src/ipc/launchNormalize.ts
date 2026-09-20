/**
 * Normalize Open Project IPC launch payloads (tolerant of missing optional fields).
 */

import type { DashboardProject, OpenProjectResult, WorkflowLaunchResult } from "./types";

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** Stable launch contract for the desktop UI. */
function normalizeLaunchResult(raw: unknown): WorkflowLaunchResult {
  const record = asRecord(raw);
  const action: WorkflowLaunchResult["action"] =
    record.action === "editor" ? "editor" : "explorer";
  const fallbackUsed = Boolean(record.fallback_used);
  const editorLaunched =
    record.editor_launched !== undefined
      ? Boolean(record.editor_launched)
      : action === "editor" && !fallbackUsed;
  const explorerOpened =
    record.explorer_opened !== undefined
      ? Boolean(record.explorer_opened)
      : action === "explorer" || fallbackUsed;

  const message =
    typeof record.message === "string" && record.message.trim()
      ? record.message
      : editorLaunched
        ? "Session updated and editor launch requested."
        : explorerOpened
          ? "Session updated. Opening project folder in File Explorer."
          : "Project open completed.";

  return {
    success: record.success !== false,
    message,
    editor_launched: editorLaunched,
    explorer_opened: explorerOpened,
    fallback_used: fallbackUsed,
    action,
    editor: typeof record.editor === "string" ? record.editor : null,
    session_id: typeof record.session_id === "number" ? record.session_id : null,
    session_started: Boolean(record.session_started),
    editor_pid: typeof record.editor_pid === "number" ? record.editor_pid : null,
  };
}

export function normalizeOpenProjectResult(raw: unknown): OpenProjectResult {
  const record = asRecord(raw);
  const project = record.project as DashboardProject | undefined;
  if (!project || typeof project.id !== "number") {
    throw new Error("launch_failed: Backend did not return a valid project record.");
  }
  return {
    project,
    launch: normalizeLaunchResult(record.launch),
  };
}
