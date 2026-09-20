import { beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

import type { BootstrapData, DashboardProject, HistoryRow, ResumePanelData } from "./types";

function project(overrides: Partial<DashboardProject> = {}): DashboardProject {
  return {
    id: 1,
    name: "demo",
    path: "C:\\demo",
    path_accessible: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    last_opened_at: null,
    preferred_ide: null,
    is_active: false,
    category: "Personal Projects",
    status: "active",
    notes: null,
    last_refreshed_at: null,
    latest_session: null,
    summary_preview: null,
    git_status: { state: "unknown", label: "No scan yet", is_git_repo: false, is_dirty: false, branch: null },
    has_resume: false,
    open_task_count: null,
    latest_scan_at: null,
    ...overrides,
  };
}

function bootstrapPayload(projects: DashboardProject[]): BootstrapData {
  return {
    config_dir: "C:\\config",
    config_path: "C:\\config\\config.json",
    database_path: "C:\\config\\graf-id.db",
    schema_version: 11,
    projects,
    app_settings: null,
  };
}

const emptyPanel: ResumePanelData = {
  startup_summary: null,
  blocker: null,
  next_step: null,
  exit_note: null,
  modified_files: [],
  stored_resume_excerpt: null,
  git_status: { state: "unknown", label: "No scan yet", is_git_repo: false, is_dirty: false, branch: null },
  has_stored_resume: false,
  latest_session: null,
  last_opened_at: null,
  open_task_count: null,
  latest_scan_at: null,
};

describe("ipc/client bootstrap cache", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    vi.resetModules();
  });

  it("refreshProjectResume does not mutate the previously-returned projects array in place (H10)", async () => {
    const { fetchBootstrap: freshFetchBootstrap, refreshProjectResume: freshRefresh } =
      await import("./client");
    invokeMock.mockResolvedValueOnce({ ok: true, data: bootstrapPayload([project({ id: 1, name: "a" })]) });
    const bootstrap = await freshFetchBootstrap();
    const projectsBefore = bootstrap.projects;

    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        project: project({ id: 1, name: "a-refreshed" }),
        resume_panel: emptyPanel,
      },
    });
    await freshRefresh(1);

    // The array reference the caller already holds must be untouched (no in-place mutation).
    expect(projectsBefore[0].name).toBe("a");
    expect(projectsBefore).not.toBe((await freshFetchBootstrap()).projects);
  });

  it("refreshProjectResume merge falls back to the cached value on an explicit null (H10 null-clobber guard)", async () => {
    const { fetchBootstrap: freshFetchBootstrap, refreshProjectResume: freshRefresh } =
      await import("./client");
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: bootstrapPayload([project({ id: 1, category: "Work" })]),
    });
    await freshFetchBootstrap();

    // mergeDashboardProject uses `??` for `category`, so an explicit JSON null in the
    // response must fall back to the cached value instead of clobbering it — this is
    // exactly the case a raw `{...prev, ...patch}` spread would get wrong (it would
    // apply the null, since the key is present).
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        project: { ...project({ id: 1, name: "a" }), category: null } as unknown as DashboardProject,
        resume_panel: emptyPanel,
      },
    });
    await freshRefresh(1);

    const after = await freshFetchBootstrap();
    expect(after.projects[0].category).toBe("Work");
  });

  it("fetchProjectHistory caches history without disturbing other cached fields", async () => {
    const { fetchBootstrap: freshFetchBootstrap, fetchProjectHistory: freshFetchHistory } =
      await import("./client");
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: bootstrapPayload([project({ id: 1, notes: "keep me" })]),
    });
    await freshFetchBootstrap();

    const rows: HistoryRow[] = [
      {
        snapshot_id: 1,
        scanned_at: "2026-01-01T00:00:00Z",
        project_name: "demo",
        scanned_at_label: "today",
        summary_preview: "ok",
        changed_files_count: 0,
        session_duration_label: null,
        findings_count: 0,
        scanned_files_count: 1,
        duration_seconds: 0.1,
        git_branch: null,
        git_dirty: null,
        is_git_repo: false,
        summary_source: "scan",
      },
    ];
    invokeMock.mockResolvedValueOnce({ ok: true, data: { history: rows } });
    await freshFetchHistory(1, { force: true });

    const after = await freshFetchBootstrap();
    expect(after.projects[0].history).toEqual(rows);
    expect(after.projects[0].notes).toBe("keep me");
  });

  it("openProjectWorkflow merges the returned project via mergeDashboardProject semantics", async () => {
    const { fetchBootstrap: freshFetchBootstrap, openProjectWorkflow: freshOpen } =
      await import("./client");
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: bootstrapPayload([project({ id: 1, category: "Work" })]),
    });
    await freshFetchBootstrap();

    const patch = {
      ...project({ id: 1, name: "a", last_opened_at: "2026-02-01T00:00:00Z" }),
      category: null,
    } as unknown as DashboardProject;
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        project: patch,
        launch: {
          success: true,
          message: "Opened",
          editor_launched: true,
          explorer_opened: false,
          fallback_used: false,
          action: "editor",
          editor: "cursor",
          session_id: 1,
          session_started: true,
        },
      },
    });
    await freshOpen(1);

    const after = await freshFetchBootstrap();
    expect(after.projects[0].last_opened_at).toBe("2026-02-01T00:00:00Z");
    expect(after.projects[0].category).toBe("Work");
  });

  it("addProject inserts the new project into the bootstrap cache immediately (M8)", async () => {
    const { fetchBootstrap: freshFetchBootstrap, addProject: freshAdd } = await import("./client");
    invokeMock.mockResolvedValueOnce({ ok: true, data: bootstrapPayload([project({ id: 1 })]) });
    await freshFetchBootstrap();

    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: { project: project({ id: 2, name: "new-project" }), message: "Added" },
    });
    await freshAdd("new-project", "C:\\new-project");

    const after = await freshFetchBootstrap();
    expect(after.projects.map((p) => p.id)).toContain(2);
  });

  it("removeProject prunes the project from the bootstrap cache immediately (M8)", async () => {
    const { fetchBootstrap: freshFetchBootstrap, removeProject: freshRemove } = await import(
      "./client"
    );
    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: bootstrapPayload([project({ id: 1 }), project({ id: 2, name: "b" })]),
    });
    await freshFetchBootstrap();

    invokeMock.mockResolvedValueOnce({
      ok: true,
      data: { project_id: 2, project_name: "b", message: "Removed" },
    });
    await freshRemove(2);

    const after = await freshFetchBootstrap();
    expect(after.projects.map((p) => p.id)).not.toContain(2);
  });
});
