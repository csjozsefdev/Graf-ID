import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AppLoadState,
  BootstrapData,
  DashboardProject,
  HistoryRow,
  OpenProjectResult,
  ProjectDetailData,
  ResumePanelData,
} from "../ipc/types";
import type { RefreshResumeResult } from "../ipc/client";
import { setMatchMediaMatches } from "../test/setup";
import { open as openDialogMock } from "@tauri-apps/plugin-dialog";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
}));

const {
  fetchProjectDetailMock,
  fetchProjectHistoryMock,
  closeProjectSessionMock,
  openProjectFolderPathMock,
  openProjectWorkflowMock,
  openProjectWithCodingAgentMock,
  previewContextImportMock,
  applyContextImportMock,
  refreshProjectResumeMock,
  removeProjectMock,
  reorderProjectsMock,
  exportProjectToFileMock,
  MockExportCancelledError,
  hideToTrayMock,
  showFromTrayMock,
  startEditorLifecycleProbeMock,
  stopEditorLifecycleProbeMock,
  startEditorReadinessProbeMock,
  stopEditorReadinessProbeMock,
} = vi.hoisted(() => {
  class MockExportCancelledError extends Error {
    constructor() {
      super("Export cancelled");
      this.name = "ExportCancelledError";
    }
  }
  return {
    fetchProjectDetailMock: vi.fn(),
    fetchProjectHistoryMock: vi.fn(),
    closeProjectSessionMock: vi.fn(),
    openProjectFolderPathMock: vi.fn().mockResolvedValue(undefined),
    openProjectWorkflowMock: vi.fn(),
    openProjectWithCodingAgentMock: vi.fn(),
    previewContextImportMock: vi.fn(),
    applyContextImportMock: vi.fn(),
    refreshProjectResumeMock: vi.fn(),
    removeProjectMock: vi.fn(),
    reorderProjectsMock: vi.fn(),
    exportProjectToFileMock: vi.fn(),
    MockExportCancelledError,
    hideToTrayMock: vi.fn().mockResolvedValue(undefined),
    showFromTrayMock: vi.fn().mockResolvedValue(undefined),
    startEditorLifecycleProbeMock: vi.fn(),
    stopEditorLifecycleProbeMock: vi.fn(),
    startEditorReadinessProbeMock: vi.fn(),
    stopEditorReadinessProbeMock: vi.fn(),
  };
});

vi.mock("../ipc/client", () => ({
  fetchProjectDetail: (...args: unknown[]) => fetchProjectDetailMock(...args),
  fetchProjectHistory: (...args: unknown[]) => fetchProjectHistoryMock(...args),
  getUserErrorMessage: (err: unknown) => (err instanceof Error ? err.message : String(err)),
  closeProjectSession: (...args: unknown[]) => closeProjectSessionMock(...args),
  openProjectFolderPath: (...args: unknown[]) => openProjectFolderPathMock(...args),
  openProjectWorkflow: (...args: unknown[]) => openProjectWorkflowMock(...args),
  openProjectWithCodingAgent: (...args: unknown[]) => openProjectWithCodingAgentMock(...args),
  previewContextImport: (...args: unknown[]) => previewContextImportMock(...args),
  applyContextImport: (...args: unknown[]) => applyContextImportMock(...args),
  refreshProjectResume: (...args: unknown[]) => refreshProjectResumeMock(...args),
  removeProject: (...args: unknown[]) => removeProjectMock(...args),
  reorderProjects: (...args: unknown[]) => reorderProjectsMock(...args),
  detectBuildCaches: vi.fn().mockResolvedValue({ caches: [] }),
  cleanBuildCache: vi.fn(),
}));

vi.mock("../utils/exportProject", () => ({
  exportProjectToFile: (...args: unknown[]) => exportProjectToFileMock(...args),
  ExportCancelledError: MockExportCancelledError,
}));

vi.mock("../utils/hideToTray", () => ({
  hideToTray: (...args: unknown[]) => hideToTrayMock(...args),
  showFromTray: (...args: unknown[]) => showFromTrayMock(...args),
}));

vi.mock("../utils/mainWindowClose", () => ({
  executeMainWindowClose: vi.fn().mockResolvedValue(undefined),
  resolveMainWindowCloseMode: vi.fn().mockReturnValue("quit"),
  setMainWindowCloseHandler: vi.fn(),
}));

vi.mock("../utils/editorSessionProbe", () => ({
  isEditorLifecycleProbeActive: vi.fn().mockReturnValue(false),
  startEditorLifecycleProbe: (...args: unknown[]) => startEditorLifecycleProbeMock(...args),
  stopEditorLifecycleProbe: (...args: unknown[]) => stopEditorLifecycleProbeMock(...args),
}));

vi.mock("../utils/editorReadinessProbe", () => ({
  capturePreLaunchEditorCount: vi.fn().mockResolvedValue(0),
  startEditorReadinessProbe: (...args: unknown[]) => startEditorReadinessProbeMock(...args),
  stopEditorReadinessProbe: (...args: unknown[]) => stopEditorReadinessProbeMock(...args),
}));

vi.mock("./grafi/ProjectWakeTransition", () => ({
  ProjectWakeTransition: (props: {
    visible: boolean;
    onHidden: () => void;
    projectName: string;
  }) => {
    // Simulate the CSS fade-out transition completing instantly once hidden.
    if (!props.visible) {
      queueMicrotask(props.onHidden);
    }
    return <div data-testid="wake-transition">{props.projectName}</div>;
  },
}));

vi.mock("./grafi/GrafiAdvisorHost", () => ({
  GrafiAdvisorHost: () => null,
}));

import { AppShell } from "./AppShell";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function gitStatus(): DashboardProject["git_status"] {
  return { state: "unknown", label: "No scan yet", is_git_repo: false, is_dirty: false, branch: null };
}

function project(overrides: Partial<DashboardProject> = {}): DashboardProject {
  return {
    id: 1,
    name: "Alpha",
    path: "C:\\alpha",
    path_accessible: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    last_opened_at: "2026-01-01T00:00:00Z",
    preferred_ide: null,
    is_active: false,
    has_open_session: false,
    category: "Personal Projects",
    status: "active",
    notes: null,
    last_refreshed_at: null,
    sidebar_order: 1,
    latest_session: null,
    summary_preview: null,
    git_status: gitStatus(),
    has_resume: false,
    open_task_count: null,
    latest_scan_at: null,
    ...overrides,
  };
}

function panel(overrides: Partial<ResumePanelData> = {}): ResumePanelData {
  return {
    startup_summary: null,
    blocker: null,
    next_step: null,
    exit_note: null,
    modified_files: [],
    stored_resume_excerpt: null,
    git_status: gitStatus(),
    has_stored_resume: false,
    latest_session: null,
    last_opened_at: null,
    open_task_count: null,
    latest_scan_at: null,
    ...overrides,
  };
}

function historyRow(overrides: Partial<HistoryRow> = {}): HistoryRow {
  return {
    snapshot_id: 1,
    scanned_at: "2026-01-01T00:00:00Z",
    project_name: "Alpha",
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
    ...overrides,
  };
}

function detailData(p: DashboardProject, panelOverrides: Partial<ResumePanelData> = {}): ProjectDetailData {
  return { project: p, resume_panel: panel(panelOverrides), history: [] };
}

function bootstrapState(
  projects: DashboardProject[],
  appSettings: BootstrapData["app_settings"] = null
): Extract<AppLoadState, { status: "ready" }> {
  const bootstrap: BootstrapData = {
    config_dir: "C:\\config",
    config_path: "C:\\config\\config.json",
    database_path: "C:\\config\\graf-id.db",
    schema_version: 11,
    projects,
    app_settings: appSettings,
  };
  return { status: "ready", bootstrap };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function launchResult(overrides: Partial<OpenProjectResult["launch"]> = {}): OpenProjectResult["launch"] {
  return {
    success: true,
    message: "Opened folder in File Explorer.",
    editor_launched: false,
    explorer_opened: false,
    fallback_used: false,
    action: "explorer",
    editor: null,
    session_id: 1,
    session_started: true,
    ...overrides,
  };
}

/** Mirrors App.tsx's own state wiring so add/remove/reorder actually update the
 * projects list AppShell receives, matching real app behavior. */
function Harness({
  initialProjects,
  appSettings = null,
}: {
  initialProjects: DashboardProject[];
  appSettings?: BootstrapData["app_settings"];
}) {
  const [state, setState] = useState(() => bootstrapState(initialProjects, appSettings));
  return (
    <AppShell
      state={state}
      onProjectAdded={(project: DashboardProject) =>
        setState((prev: Extract<AppLoadState, { status: "ready" }>) => {
          const exists = prev.bootstrap.projects.some((p) => p.id === project.id);
          const projects = exists
            ? prev.bootstrap.projects.map((p) => (p.id === project.id ? project : p))
            : [...prev.bootstrap.projects, project];
          return { status: "ready", bootstrap: { ...prev.bootstrap, projects } };
        })
      }
      onProjectRemoved={(projectId: number) =>
        setState((prev: Extract<AppLoadState, { status: "ready" }>) => ({
          status: "ready",
          bootstrap: {
            ...prev.bootstrap,
            projects: prev.bootstrap.projects.filter((p) => p.id !== projectId),
          },
        }))
      }
      onProjectsReordered={(projects: DashboardProject[]) =>
        setState((prev: Extract<AppLoadState, { status: "ready" }>) => ({
          status: "ready",
          bootstrap: { ...prev.bootstrap, projects },
        }))
      }
    />
  );
}

function renderShell(
  projects: DashboardProject[],
  appSettings: BootstrapData["app_settings"] = null
) {
  return render(<Harness initialProjects={projects} appSettings={appSettings} />);
}

function appSettingsFixture(
  overrides: Partial<NonNullable<BootstrapData["app_settings"]>> = {}
): NonNullable<BootstrapData["app_settings"]> {
  return {
    data_dir: "C:\\data",
    logs_dir: "C:\\logs",
    config_dir: "C:\\config",
    config_path: "C:\\config\\config.json",
    default_project_opener: "cursor",
    usage_journal_enabled: false,
    debug_timing_enabled: false,
    opener_options: [],
    coding_agents: [],
    ...overrides,
  };
}

async function selectProjectByName(name: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("option", { name: new RegExp(name) }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AppShell — cross-project state isolation (C2, H9/H14, M10, L6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setMatchMediaMatches(true); // reduced motion — skips the wake-transition video delay
    fetchProjectDetailMock.mockImplementation((id: number) => {
      const p = id === 1 ? project({ id: 1, name: "Alpha" }) : project({ id: 2, name: "Bravo" });
      return Promise.resolve(detailData(p));
    });
    fetchProjectHistoryMock.mockImplementation((id: number) =>
      Promise.resolve([historyRow({ snapshot_id: id, project_name: id === 1 ? "Alpha" : "Bravo" })])
    );
  });

  afterEach(() => {
    setMatchMediaMatches(false);
  });

  it("a stale Refresh response for A does not overwrite B's history/scan-health after switching (C2, stale history response)", async () => {
    const user = userEvent.setup();
    const alpha = project({ id: 1, name: "Alpha" });
    const bravo = project({ id: 2, name: "Bravo" });
    renderShell([alpha, bravo]);

    await screen.findByRole("heading", { name: "Alpha" });

    const refreshDeferred = deferred<Awaited<ReturnType<typeof refreshProjectResumeMock>>>();
    refreshProjectResumeMock.mockReturnValueOnce(refreshDeferred.promise);

    await user.click(screen.getByRole("button", { name: /Refresh context/i }));
    expect(refreshProjectResumeMock).toHaveBeenCalledWith(1);

    // Switch to Bravo before Alpha's refresh resolves.
    await selectProjectByName("Bravo");
    await screen.findByRole("heading", { name: "Bravo" });

    // Alpha's refresh now resolves with data clearly tagged as Alpha's.
    await act(async () => {
      refreshDeferred.resolve({
        project: project({ id: 1, name: "Alpha" }),
        resume_panel: panel(),
      } as RefreshResumeResult);
      await Promise.resolve();
    });

    // Bravo must still be shown; Alpha's late response must not replace it.
    expect(screen.getByRole("heading", { name: "Bravo" })).toBeInTheDocument();

    // History tab must show Bravo's rows, not Alpha's stale response.
    await user.click(screen.getByRole("button", { name: "History" }));
    expect(await screen.findByRole("heading", { name: /History — Bravo/ })).toBeInTheDocument();
  });

  it("switching to B while exporting A shows A's project name in the completion notice, not a corrupted current-project message", async () => {
    const user = userEvent.setup();
    const alpha = project({ id: 1, name: "Alpha" });
    const bravo = project({ id: 2, name: "Bravo" });
    renderShell([alpha, bravo]);
    await screen.findByRole("heading", { name: "Alpha" });

    const exportDeferred = deferred<string>();
    exportProjectToFileMock.mockReturnValueOnce(exportDeferred.promise);

    await user.click(screen.getByRole("button", { name: "JSON" }));
    expect(exportProjectToFileMock).toHaveBeenCalledWith(1, "json");

    await selectProjectByName("Bravo");
    await screen.findByRole("heading", { name: "Bravo" });

    await act(async () => {
      exportDeferred.resolve("C:\\exports\\alpha.json");
      await Promise.resolve();
    });

    expect(await screen.findByText(/Exported Alpha to C:\\exports\\alpha\.json/)).toBeInTheDocument();
  });

  it("a stale project-detail response for A does not clobber B's loading/error state (stale detail response)", async () => {
    const alpha = project({ id: 1, name: "Alpha" });
    const bravo = project({ id: 2, name: "Bravo" });

    const alphaDeferred = deferred<ProjectDetailData>();
    fetchProjectDetailMock.mockImplementation((id: number) => {
      if (id === 1) {
        return alphaDeferred.promise;
      }
      return Promise.resolve(detailData(bravo));
    });

    renderShell([alpha, bravo]);

    // Alpha's initial detail load is stuck pending (auto-selected as sidebar_order 1).
    expect(screen.getByText(/Loading…/)).toBeInTheDocument();

    await selectProjectByName("Bravo");
    await screen.findByRole("heading", { name: "Bravo" });
    expect(screen.queryByText(/Loading…/)).not.toBeInTheDocument();

    // Alpha's slow response now arrives — must not flip Bravo's panel back to loading.
    await act(async () => {
      alphaDeferred.resolve(detailData(alpha));
      await Promise.resolve();
    });

    expect(screen.getByRole("heading", { name: "Bravo" })).toBeInTheDocument();
    expect(screen.queryByText(/Loading…/)).not.toBeInTheDocument();
  });

  it("navigating to B mid open-project does not corrupt B's detail state, and A's fallback notice still applies to A (open-project közbeni navigáció)", async () => {
    const user = userEvent.setup();
    const alpha = project({ id: 1, name: "Alpha" });
    const bravo = project({ id: 2, name: "Bravo" });
    renderShell([alpha, bravo]);
    await screen.findByRole("heading", { name: "Alpha" });

    const openDeferred = deferred<OpenProjectResult>();
    openProjectWorkflowMock.mockReturnValueOnce(openDeferred.promise);

    await user.click(screen.getByRole("button", { name: /Open project/i }));

    await waitFor(() => expect(openProjectWorkflowMock).toHaveBeenCalledWith(1));

    await selectProjectByName("Bravo");
    await screen.findByRole("heading", { name: "Bravo" });

    await act(async () => {
      openDeferred.resolve({
        project: project({ id: 1, name: "Alpha" }),
        launch: launchResult({ message: "No editor available for Alpha. Opened folder in File Explorer." }),
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    // Bravo stays on screen and functional; the notice references Alpha, not Bravo.
    expect(screen.getByRole("heading", { name: "Bravo" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/No editor available for Alpha/)).toBeInTheDocument()
    );
  });

  it("removing project B while A's refresh is in flight does not crash and both complete correctly (remove másik projekt async művelet közben)", async () => {
    const user = userEvent.setup();
    const alpha = project({ id: 1, name: "Alpha" });
    const bravo = project({ id: 2, name: "Bravo" });
    renderShell([alpha, bravo]);
    await screen.findByRole("heading", { name: "Alpha" });

    const refreshDeferred = deferred<Awaited<ReturnType<typeof refreshProjectResumeMock>>>();
    refreshProjectResumeMock.mockReturnValueOnce(refreshDeferred.promise);
    await user.click(screen.getByRole("button", { name: /Refresh context/i }));

    // Open Bravo's row menu and remove it while Alpha's refresh is still pending.
    await user.click(screen.getByRole("button", { name: /Project actions for Bravo/i }));
    await user.click(screen.getByRole("menuitem", { name: /Remove from Graf-Id/i }));
    removeProjectMock.mockResolvedValueOnce({
      project_id: 2,
      project_name: "Bravo",
      message: "Removed Bravo.",
    });
    await user.click(screen.getByRole("button", { name: "Remove from Graf-Id" }));

    await waitFor(() => expect(removeProjectMock).toHaveBeenCalledWith(2));
    expect(screen.queryByRole("option", { name: /Bravo/ })).not.toBeInTheDocument();

    await act(async () => {
      refreshDeferred.resolve({
        project: project({ id: 1, name: "Alpha" }),
        resume_panel: panel(),
      } as RefreshResumeResult);
      await Promise.resolve();
    });

    expect(await screen.findByText(/Project context updated\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();
  });

  it("an editor-close event for a project with no open session is ignored (editor closed nem aktív projekten)", async () => {
    const alpha = project({ id: 1, name: "Alpha", has_open_session: false });
    renderShell([alpha]);
    await screen.findByRole("heading", { name: "Alpha" });

    // Directly exercise the lifecycle-probe callback wiring exposed via the mock.
    // No open-project flow ran, so nothing has registered a callback — assert
    // no exit-note dialog is present, which would indicate a spurious trigger.
    expect(screen.queryByRole("dialog", { name: /End session/i })).not.toBeInTheDocument();
  });

  it("a second project's editor-close event is queued while the first project's dialog is open, and replays after it closes (M10)", async () => {
    const user = userEvent.setup();
    const alpha = project({ id: 1, name: "Alpha", has_open_session: true });
    const bravo = project({ id: 2, name: "Bravo", has_open_session: true });
    // The initial detail-load-on-select must keep has_open_session consistent with the
    // bootstrap fixture, or the merge would (correctly) apply the fetched false over it.
    fetchProjectDetailMock.mockImplementation((id: number) =>
      Promise.resolve(detailData(id === 1 ? alpha : bravo))
    );
    renderShell([alpha, bravo]);
    await screen.findByRole("heading", { name: "Alpha" });

    // Drive Alpha's open-project flow to register the lifecycle-probe callback.
    const openDeferred = deferred<OpenProjectResult>();
    openProjectWorkflowMock.mockReturnValueOnce(openDeferred.promise);
    await user.click(screen.getByRole("button", { name: /Open project/i }));
    await waitFor(() => expect(openProjectWorkflowMock).toHaveBeenCalledWith(1));
    await act(async () => {
      openDeferred.resolve({
        project: project({ id: 1, name: "Alpha", has_open_session: true }),
        launch: launchResult({
          editor_launched: true,
          fallback_used: false,
          action: "editor",
          editor: "cursor",
          editor_pid: 4242,
        }),
      });
      await Promise.resolve();
    });

    // The readiness probe's onReady callback starts the lifecycle probe.
    const readinessArgs = startEditorReadinessProbeMock.mock.calls.at(-1)?.[0];
    expect(readinessArgs).toBeTruthy();
    await act(async () => {
      readinessArgs.onReady();
    });

    const lifecycleArgs = startEditorLifecycleProbeMock.mock.calls.at(-1)?.[0];
    expect(lifecycleArgs).toBeTruthy();

    // Alpha's editor closes → its exit-note dialog opens.
    act(() => {
      lifecycleArgs.onEditorCloseDetected();
    });
    expect(await screen.findByText(/Alpha/, { selector: "strong" })).toBeInTheDocument();

    // Bravo's close is detected while Alpha's dialog is still open — must be queued, not dropped.
    act(() => {
      lifecycleArgs.onEditorCloseDetected(); // Alpha again — should be a no-op (already prompted)
    });

    // Finish Alpha's dialog via "End without notes".
    closeProjectSessionMock.mockResolvedValueOnce({
      project: project({ id: 1, name: "Alpha", has_open_session: false }),
      resume_panel: panel(),
      message: "Session closed for Alpha.",
      session_closed: true,
    });
    await user.click(screen.getByRole("button", { name: "End without notes" }));
    await waitFor(() => expect(closeProjectSessionMock).toHaveBeenCalledWith(1, expect.anything()));
  });

  it("stops the editor lifecycle probe on unmount (component unmount probe cleanup, L6)", async () => {
    const alpha = project({ id: 1, name: "Alpha" });
    const { unmount } = renderShell([alpha]);
    await screen.findByRole("heading", { name: "Alpha" });

    unmount();

    expect(stopEditorReadinessProbeMock).toHaveBeenCalled();
    expect(stopEditorLifecycleProbeMock).toHaveBeenCalled();
  });
});

describe("AppShell — IPC timeouts (H7, H8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setMatchMediaMatches(true);
    fetchProjectDetailMock.mockImplementation((id: number) =>
      Promise.resolve(detailData(project({ id, name: id === 1 ? "Alpha" : "Bravo" })))
    );
    fetchProjectHistoryMock.mockResolvedValue([]);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    setMatchMediaMatches(false);
  });

  it("Open Project recovers from a hung backend call instead of staying busy forever (H7)", async () => {
    const alpha = project({ id: 1, name: "Alpha" });
    renderShell([alpha]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();

    // Never resolves — simulates a hung Python subprocess/Tauri command.
    openProjectWorkflowMock.mockReturnValueOnce(new Promise<never>(() => {}));

    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(openProjectWorkflowMock).toHaveBeenCalledWith(1);
    expect(screen.getByRole("button", { name: "Opening…" })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    // Busy state must have recovered — button text is back to normal and re-enabled.
    expect(screen.getByRole("button", { name: "Open project" })).not.toBeDisabled();
    expect(screen.getByText(/did not respond in time/)).toBeInTheDocument();
  });

  it("closing the session recovers from a hung backend call, and the window stays closable (H8)", async () => {
    const alpha = project({ id: 1, name: "Alpha", has_open_session: true });
    // The initial detail-load-on-select must keep has_open_session consistent with the
    // bootstrap fixture, or the (correct) merge would apply the fetched false over it.
    fetchProjectDetailMock.mockImplementation(() => Promise.resolve(detailData(alpha)));
    renderShell([alpha]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();

    // Drive Alpha's open-project flow so the lifecycle probe callback is registered.
    openProjectWorkflowMock.mockResolvedValueOnce({
      project: project({ id: 1, name: "Alpha", has_open_session: true }),
      launch: launchResult({
        editor_launched: true,
        fallback_used: false,
        action: "editor",
        editor: "cursor",
        editor_pid: 777,
      }),
    });
    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const readinessArgs = startEditorReadinessProbeMock.mock.calls.at(-1)?.[0];
    act(() => {
      readinessArgs.onReady();
    });
    const lifecycleArgs = startEditorLifecycleProbeMock.mock.calls.at(-1)?.[0];

    act(() => {
      lifecycleArgs.onEditorCloseDetected();
    });
    expect(screen.getByText(/Alpha/, { selector: "strong" })).toBeInTheDocument();

    // Never resolves — simulates a hung close-session call.
    closeProjectSessionMock.mockReturnValueOnce(new Promise<never>(() => {}));
    fireEvent.click(screen.getByRole("button", { name: "End without notes" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("button", { name: "Saving…" })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });

    // closeSessionBusy must have recovered: the dialog's own buttons are re-enabled again
    // (mirrors the real guard: mainWindowClose only refuses to close while this is true).
    expect(screen.getByRole("button", { name: "End without notes" })).not.toBeDisabled();
    expect(screen.getByText(/did not respond in time/)).toBeInTheDocument();
  });
});

describe("AppShell — Coding Agent launch routing (M5/M7/M8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setMatchMediaMatches(true);
    fetchProjectDetailMock.mockImplementation((id: number) =>
      Promise.resolve(detailData(project({ id, name: id === 1 ? "Alpha" : "Bravo" })))
    );
    fetchProjectHistoryMock.mockResolvedValue([]);
  });

  afterEach(() => {
    setMatchMediaMatches(false);
  });

  it("routes to the coding-agent launcher (not openProjectWorkflow, no wake transition) when the project's own opener is an agent", async () => {
    const alpha = project({ id: 1, name: "Alpha", preferred_ide: "agent:claude-code" });
    // The initial detail-load-on-select must keep preferred_ide consistent with the
    // bootstrap fixture, or the (correct) merge would clobber it with the default null.
    fetchProjectDetailMock.mockImplementation(() => Promise.resolve(detailData(alpha)));
    openProjectWithCodingAgentMock.mockResolvedValueOnce({
      executable: "C:\\tools\\claude.cmd",
      args: [],
      cwd: "C:\\alpha",
      display_name: "Claude Code",
    });
    renderShell([alpha]);
    await act(async () => {});
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {});

    expect(openProjectWithCodingAgentMock).toHaveBeenCalledWith("claude-code", 1);
    expect(openProjectWorkflowMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("wake-transition")).not.toBeInTheDocument();
    expect(startEditorReadinessProbeMock).not.toHaveBeenCalled();
    expect(startEditorLifecycleProbeMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Claude Code started in C:\\alpha/)).toBeInTheDocument();
  });

  it("falls back to the global default opener (from a fresh Settings save) when the project has no opener override", async () => {
    const alpha = project({ id: 1, name: "Alpha", preferred_ide: null });
    openProjectWithCodingAgentMock.mockResolvedValueOnce({
      executable: "codex",
      args: [],
      cwd: "C:\\alpha",
      display_name: "Codex CLI",
    });
    renderShell([alpha], appSettingsFixture({ default_project_opener: "agent:codex-cli" }));
    await act(async () => {});

    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {});

    expect(openProjectWithCodingAgentMock).toHaveBeenCalledWith("codex-cli", 1);
    expect(openProjectWorkflowMock).not.toHaveBeenCalled();
  });

  it("still uses the normal editor flow (wake transition + openProjectWorkflow) when the opener is an editor, not an agent", async () => {
    const alpha = project({ id: 1, name: "Alpha", preferred_ide: null });
    openProjectWorkflowMock.mockResolvedValueOnce({
      project: project({ id: 1, name: "Alpha" }),
      launch: launchResult({ editor_launched: true, action: "editor", editor: "cursor" }),
    });
    renderShell([alpha], appSettingsFixture({ default_project_opener: "cursor" }));
    await act(async () => {});

    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {});

    expect(openProjectWorkflowMock).toHaveBeenCalledWith(1);
    expect(openProjectWithCodingAgentMock).not.toHaveBeenCalled();
  });

  it("reports a coding-agent launch failure without leaving Open Project stuck busy", async () => {
    const alpha = project({ id: 1, name: "Alpha", preferred_ide: "agent:claude-code" });
    fetchProjectDetailMock.mockImplementation(() => Promise.resolve(detailData(alpha)));
    openProjectWithCodingAgentMock.mockRejectedValueOnce(new Error("Claude Code was not found on PATH."));
    renderShell([alpha]);
    await act(async () => {});

    fireEvent.click(screen.getByRole("button", { name: /Open project/i }));
    await act(async () => {});

    expect(screen.getByText("Claude Code was not found on PATH.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open project" })).not.toBeDisabled();
  });
});

describe("AppShell — context import (validate, preview, explicit confirmation)", () => {
  const previewFor = (over: Record<string, unknown> = {}) => ({
    project_id: 1,
    project_name: "Alpha",
    handoff_project_name: "Alpha",
    name_matches: true,
    current_notes: null,
    block: "Imported handoff (2026-09-20) from Alpha\nStatus: Checkout done",
    proposed_notes_append: "Imported handoff",
    fingerprint: "fp-1",
    warnings: [],
    ignored_keys: [],
    fits: true,
    files_not_imported: 0,
    ...over,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    setMatchMediaMatches(true);
    fetchProjectDetailMock.mockImplementation((id: number) =>
      Promise.resolve(detailData(project({ id, name: id === 1 ? "Alpha" : "Bravo" })))
    );
    fetchProjectHistoryMock.mockResolvedValue([]);
  });

  afterEach(() => {
    setMatchMediaMatches(false);
  });

  it("previews first and writes nothing until the user confirms", async () => {
    vi.mocked(openDialogMock).mockResolvedValueOnce("C:\in\alpha.json");
    previewContextImportMock.mockResolvedValueOnce(previewFor());
    applyContextImportMock.mockResolvedValueOnce({ project_id: 1, notes: "n", message: "ok" });
    renderShell([project({ id: 1, name: "Alpha" })]);
    await act(async () => {});

    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    await act(async () => {});

    expect(previewContextImportMock).toHaveBeenCalledWith(1, "C:\in\alpha.json");
    expect(applyContextImportMock).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: /Import context into Alpha/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Import into project notes" }));
    await act(async () => {});

    expect(applyContextImportMock).toHaveBeenCalledWith(1, "C:\in\alpha.json", "append", "fp-1", true);
    expect(screen.queryByRole("dialog", { name: /Import context/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Imported context into the notes of Alpha/)).toBeInTheDocument();
  });

  it("cancelling the dialog or the file picker never applies anything", async () => {
    vi.mocked(openDialogMock).mockResolvedValueOnce(null);
    renderShell([project({ id: 1, name: "Alpha" })]);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    await act(async () => {});
    expect(previewContextImportMock).not.toHaveBeenCalled();

    vi.mocked(openDialogMock).mockResolvedValueOnce("C:\in\alpha.json");
    previewContextImportMock.mockResolvedValueOnce(previewFor());
    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await act(async () => {});
    expect(screen.queryByRole("dialog", { name: /Import context/ })).not.toBeInTheDocument();
    expect(applyContextImportMock).not.toHaveBeenCalled();
  });

  it("shows a validation failure from the preview as a notice and opens no dialog", async () => {
    vi.mocked(openDialogMock).mockResolvedValueOnce("C:\in\bad.json");
    previewContextImportMock.mockRejectedValueOnce(new Error("Unsupported schema_version '0.2'."));
    renderShell([project({ id: 1, name: "Alpha" })]);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    await act(async () => {});
    expect(screen.getByText("Unsupported schema_version '0.2'.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /Import context/ })).not.toBeInTheDocument();
  });

  it("keeps the dialog open with the error when the apply is refused (e.g. notes changed)", async () => {
    vi.mocked(openDialogMock).mockResolvedValueOnce("C:\in\alpha.json");
    previewContextImportMock.mockResolvedValueOnce(previewFor());
    applyContextImportMock.mockRejectedValueOnce(new Error("The project notes changed since the preview."));
    renderShell([project({ id: 1, name: "Alpha" })]);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: "Import into project notes" }));
    await act(async () => {});
    expect(screen.getByText("The project notes changed since the preview.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /Import context/ })).toBeInTheDocument();
  });
});
