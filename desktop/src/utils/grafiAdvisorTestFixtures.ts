import type { DashboardProject, ResumePanelData } from "../ipc/types";

export function recentIso(hoursAgo = 1): string {
  return new Date(Date.now() - hoursAgo * 60 * 60 * 1000).toISOString();
}

export function healthyProject(overrides: Partial<DashboardProject> = {}): DashboardProject {
  const recent = recentIso(1);
  return {
    id: 1,
    name: "Demo",
    path: "C:/demo",
    path_accessible: true,
    created_at: recent,
    updated_at: recent,
    last_opened_at: recent,
    preferred_ide: null,
    is_active: false,
    category: "Personal Projects",
    status: "active",
    notes: null,
    last_refreshed_at: recent,
    latest_session: null,
    summary_preview: null,
    git_status: {
      state: "clean",
      label: "Clean",
      is_git_repo: true,
      is_dirty: false,
      branch: "main",
    },
    has_resume: true,
    open_task_count: null,
    latest_scan_at: recent,
    ...overrides,
  };
}

export function healthyPanel(overrides: Partial<ResumePanelData> = {}): ResumePanelData {
  const recent = recentIso(1);
  return {
    startup_summary: null,
    blocker: null,
    next_step: null,
    exit_note: null,
    modified_files: [],
    stored_resume_excerpt: null,
    git_status: {
      state: "clean",
      label: "Clean",
      is_git_repo: true,
      is_dirty: false,
      branch: "main",
    },
    has_stored_resume: true,
    latest_session: null,
    last_opened_at: recent,
    open_task_count: null,
    latest_scan_at: recent,
    last_refreshed_at: recent,
    mvp_sections: [],
    ...overrides,
  };
}
