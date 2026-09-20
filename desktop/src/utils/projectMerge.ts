import type { DashboardProject } from "../ipc/types";
import { DEFAULT_PROJECT_CATEGORY } from "./projectCategories";

const UNKNOWN_GIT_STATUS: DashboardProject["git_status"] = {
  state: "unknown",
  label: "No scan yet",
  is_git_repo: false,
  is_dirty: false,
  branch: null,
};

/** Merge open-project / detail patches without dropping dashboard-only fields. */
export function mergeDashboardProject(
  base: DashboardProject | undefined,
  patch: DashboardProject
): DashboardProject {
  if (!base) {
    return {
      ...patch,
      path_accessible: patch.path_accessible ?? true,
      load_error: patch.load_error ?? null,
      category: patch.category ?? DEFAULT_PROJECT_CATEGORY,
      status: patch.status ?? "active",
      notes: patch.notes ?? null,
      last_refreshed_at: patch.last_refreshed_at ?? null,
      git_status: patch.git_status ?? UNKNOWN_GIT_STATUS,
      latest_session: patch.latest_session ?? null,
      summary_preview: patch.summary_preview ?? null,
      has_resume: patch.has_resume ?? false,
      open_task_count: patch.open_task_count ?? null,
      latest_scan_at: patch.latest_scan_at ?? null,
    };
  }
  return {
    ...base,
    id: patch.id,
    name: patch.name,
    path: patch.path,
    path_accessible: patch.path_accessible ?? base.path_accessible ?? true,
    load_error: patch.load_error !== undefined ? patch.load_error : base.load_error,
    created_at: patch.created_at,
    updated_at: patch.updated_at,
    last_opened_at: patch.last_opened_at,
    preferred_ide: patch.preferred_ide,
    is_active: patch.is_active,
    category: patch.category ?? base.category ?? DEFAULT_PROJECT_CATEGORY,
    status: patch.status ?? base.status ?? "active",
    notes: patch.notes !== undefined ? patch.notes : base.notes,
    last_refreshed_at:
      patch.last_refreshed_at !== undefined
        ? patch.last_refreshed_at
        : base.last_refreshed_at,
    latest_session: patch.latest_session ?? base.latest_session,
    summary_preview: patch.summary_preview ?? base.summary_preview,
    git_status: patch.git_status ?? base.git_status,
    has_resume: patch.has_resume ?? base.has_resume,
    open_task_count: patch.open_task_count ?? base.open_task_count,
    latest_scan_at: patch.latest_scan_at ?? base.latest_scan_at,
    has_open_session: patch.has_open_session ?? base.has_open_session,
  };
}
