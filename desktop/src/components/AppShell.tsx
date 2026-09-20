import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AppLoadState,
  AppSettingsData,
  DashboardProject,
  HistoryRow,
  NavSection,
  ProjectDetailData,
} from "../ipc/types";
import {
  applyContextImport,
  previewContextImport,
  fetchProjectDetail,
  fetchProjectHistory,
  getUserErrorMessage,
  closeProjectSession,
  openProjectFolderPath,
  openProjectWithCodingAgent,
  openProjectWorkflow,
  refreshProjectResume,
  removeProject,
} from "../ipc/client";
import { agentIdFromOpenerValue } from "../utils/codingAgents";
import { AddProjectDialog } from "./AddProjectDialog";
import { BuildCacheCard } from "./BuildCacheCard";
import { CloseSessionDialog } from "./CloseSessionDialog";
import type { CloseSessionFormValues } from "./CloseSessionDialog";
import { RemoveProjectDialog } from "./RemoveProjectDialog";
import { EmptyState } from "./EmptyState";
import { HistorySection } from "./HistorySection";
import { NavSidebar } from "./NavSidebar";
import { ProjectDetailHeader } from "./ProjectDetailHeader";
import { ResumePanel } from "./ResumePanel";
import { WakePanel } from "./WakePanel";
import { Settings } from "./Settings";
import type { ContextImportMode, ContextImportPreview, ExportFormat } from "../ipc/client";
import { open as openFileDialog } from "@tauri-apps/plugin-dialog";
import { ImportContextDialog } from "./ImportContextDialog";
import { reorderProjects } from "../ipc/client";
import { sortProjectsForSidebar } from "../utils/projectOrdering";
import { ExportCancelledError, exportProjectToFile } from "../utils/exportProject";
import { hideToTray, showFromTray } from "../utils/hideToTray";
import {
  executeMainWindowClose,
  resolveMainWindowCloseMode,
  setMainWindowCloseHandler,
} from "../utils/mainWindowClose";
import { isEditorLifecycleProbeActive } from "../utils/editorSessionProbe";
import { mergeDashboardProject } from "../utils/projectMerge";
import {
  startEditorLifecycleProbe,
  stopEditorLifecycleProbe,
} from "../utils/editorSessionProbe";
import {
  capturePreLaunchEditorCount,
  startEditorReadinessProbe,
  stopEditorReadinessProbe,
} from "../utils/editorReadinessProbe";
import {
  beginProjectWakeLaunch,
  createProjectWakeUiState,
  projectWakeEditorReady,
  projectWakeLaunchFailed,
  projectWakeLaunchWaiting,
  skipProjectWakeIntro,
  type ProjectWakeUiState,
} from "../utils/projectWakeLaunch";
import { projectHasOpenSession } from "../utils/sessionActive";
import { ProjectWakeTransition } from "./grafi/ProjectWakeTransition";
import { GrafiAdvisorHost } from "./grafi/GrafiAdvisorHost";
import { GrafiHelpProvider } from "./grafi/GrafiHelpProvider";
import grafIdLogo from "../assets/graf-id-logo-transparent.png";
import {
  getProjectWakeLaunchDelayMs,
  prefersReducedMotion,
} from "../utils/projectWakeTiming";
import { withTimeout } from "../utils/withTimeout";

// No IPC call may block a busy flag forever (H7/H8) — each is bounded, generously,
// against a hung Python subprocess or Tauri command.
const PRE_LAUNCH_PROBE_TIMEOUT_MS = 10_000;
const OPEN_PROJECT_TIMEOUT_MS = 30_000;
const CLOSE_SESSION_TIMEOUT_MS = 20_000;

interface ProjectWakeSnapshot {
  projectId: number;
  projectName: string;
  projectPath: string;
  preferredEditor: string | null;
}

interface ProjectWakeTransitionState extends ProjectWakeUiState {
  snapshot: ProjectWakeSnapshot;
}

type ProjectWakePostFadeAction =
  | { type: "hide_tray" }
  | { type: "explorer"; projectPath: string; notice: string; projectId: number }
  | { type: "notice_detail"; notice: string; projectId: number }
  | { type: "error"; message: string };

interface AppShellProps {
  state: Extract<AppLoadState, { status: "ready" }>;
  onProjectAdded: (project: DashboardProject) => void;
  onProjectRemoved: (projectId: number) => void;
  onProjectsReordered: (projects: DashboardProject[]) => void;
}

export function AppShell({ state, onProjectAdded, onProjectRemoved, onProjectsReordered }: AppShellProps) {
  const [nav, setNav] = useState<NavSection>("dashboard");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailCache, setDetailCache] = useState<Record<number, ProjectDetailData>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [historyRows, setHistoryRows] = useState<HistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [projectPatches, setProjectPatches] = useState<Record<number, DashboardProject>>({});
  /** Per-project busy flags — a slow refresh/export for project A must never disable
   * project B's own buttons, and a stale response for A must never write into B's display state. */
  const [projectBusy, setProjectBusy] = useState<
    Record<number, { refreshing?: boolean; exporting?: boolean }>
  >({});
  const [openProjectBusy, setOpenProjectBusy] = useState(false);
  const [importState, setImportState] = useState<{
    projectId: number;
    filePath: string;
    fileName: string;
    preview: ContextImportPreview;
  } | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  /** Mirrors the latest saved app_settings so agent-vs-editor Open Project
   * routing sees a fresh default_project_opener/coding_agents even when the
   * user edits Settings mid-session (bootstrap.app_settings is a load-time
   * snapshot only). Settings reports its own saves back via onSettingsSaved. */
  const [appSettingsOverride, setAppSettingsOverride] = useState<AppSettingsData | null>(
    null
  );
  const [addProjectOpen, setAddProjectOpen] = useState(false);
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<DashboardProject | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [wakeDismissed, setWakeDismissed] = useState<Record<number, boolean>>({});
  const [closeSessionOpen, setCloseSessionOpen] = useState(false);
  const [closeSessionBusy, setCloseSessionBusy] = useState(false);
  const [closeSessionError, setCloseSessionError] = useState<string | null>(null);
  const [closeSessionProjectId, setCloseSessionProjectId] = useState<number | null>(null);
  const [wakeTransition, setWakeTransition] = useState<ProjectWakeTransitionState | null>(
    null
  );
  const detailLoadSeq = useRef(0);
  const historyLoadSeq = useRef(0);
  const launchTimerRef = useRef<number | null>(null);
  const launchStartedRef = useRef(false);
  const wakeSnapshotRef = useRef<ProjectWakeSnapshot | null>(null);
  const postFadeActionRef = useRef<ProjectWakePostFadeAction | null>(null);
  const wakeOverlayDismissedOnlyRef = useRef(false);
  const hideToTrayCalledRef = useRef(false);
  const shellMountedRef = useRef(true);
  /** Live mirror of `selectedId`, readable from async completion handlers so a late
   * response can tell whether it still targets the project currently on screen. */
  const selectedIdRef = useRef<number | null>(null);
  /** Editor-close events for a project other than the one currently in the exit-note
   * dialog are queued here instead of being dropped (M10). */
  const pendingEditorCloseRef = useRef<Set<number>>(new Set());
  const closeSessionOpenRef = useRef(false);
  const closeSessionBusyRef = useRef(false);
  const exitNotePromptedForProjectRef = useRef<number | null>(null);

  useEffect(() => {
    closeSessionOpenRef.current = closeSessionOpen;
  }, [closeSessionOpen]);

  useEffect(() => {
    closeSessionBusyRef.current = closeSessionBusy;
  }, [closeSessionBusy]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const bootstrap = state.bootstrap;
  const effectiveAppSettings = appSettingsOverride ?? bootstrap?.app_settings ?? null;

  useEffect(() => {
    shellMountedRef.current = true;
    return () => {
      shellMountedRef.current = false;
      if (launchTimerRef.current !== null) {
        window.clearTimeout(launchTimerRef.current);
        launchTimerRef.current = null;
      }
      stopEditorReadinessProbe();
      stopEditorLifecycleProbe();
    };
  }, []);

  /** Merge one busy flag for one project; drops the entry once nothing is busy for it. */
  const setProjectBusyFlag = useCallback(
    (projectId: number, key: "refreshing" | "exporting", value: boolean) => {
      setProjectBusy((prev) => {
        const current = prev[projectId];
        if (!value && !current) {
          return prev;
        }
        const nextEntry = { ...current, [key]: value };
        const hasAny = Boolean(nextEntry.refreshing || nextEntry.exporting);
        if (!hasAny) {
          if (!(projectId in prev)) {
            return prev;
          }
          const next = { ...prev };
          delete next[projectId];
          return next;
        }
        return { ...prev, [projectId]: nextEntry };
      });
    },
    []
  );

  const projects = useMemo(() => {
    const base = bootstrap?.projects ?? [];
    return base.map((project) => {
      const patch = projectPatches[project.id];
      return patch ? mergeDashboardProject(project, patch) : project;
    });
  }, [bootstrap?.projects, projectPatches]);
  const hasProjects = projects.length > 0;

  useEffect(() => {
    if (bootstrap && hasProjects && selectedId === null) {
      const sorted = sortProjectsForSidebar(projects);
      setSelectedId(sorted[0]?.id ?? null);
    }
  }, [bootstrap, hasProjects, projects, selectedId]);

  useEffect(() => {
    if (selectedId !== null && hasProjects && !projects.some((p) => p.id === selectedId)) {
      setSelectedId(sortProjectsForSidebar(projects)[0]?.id ?? null);
    }
  }, [hasProjects, projects, selectedId]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId]
  );

  const loadDetail = useCallback(
    async (projectId: number, force = false) => {
      if (!force && detailCache[projectId]) {
        return;
      }
      const seq = ++detailLoadSeq.current;
      // detailLoading/detailError describe whatever project is on screen right now —
      // only touch them when this call is (still, or already) for that project, so a
      // background reload for a project the user has navigated away from can't flip
      // the currently-selected project's loading/error state (C2).
      const stillCurrent = () => projectId === selectedIdRef.current;
      if (stillCurrent()) {
        setDetailLoading(true);
        setDetailError(null);
      }
      try {
        const data = await fetchProjectDetail(projectId);
        if (seq !== detailLoadSeq.current) {
          return;
        }
        setDetailCache((prev) => ({ ...prev, [projectId]: data }));
        setProjectPatches((prev) => {
          const base = bootstrap?.projects.find((p) => p.id === data.project.id);
          return {
            ...prev,
            [data.project.id]: mergeDashboardProject(base, data.project),
          };
        });
      } catch (err) {
        if (seq === detailLoadSeq.current && stillCurrent()) {
          setDetailError(getUserErrorMessage(err));
        }
      } finally {
        if (seq === detailLoadSeq.current && stillCurrent()) {
          setDetailLoading(false);
        }
      }
    },
    [detailCache, bootstrap?.projects]
  );

  const handleRefreshResume = useCallback(async () => {
    const targetId = selectedId;
    if (targetId === null || selectedProject?.path_accessible === false) {
      if (selectedProject?.path_accessible === false) {
        setActionNotice(
          "Registered folder not found. Restore the path on disk before refreshing context."
        );
      }
      return;
    }
    if (projectBusy[targetId]?.refreshing) {
      // Already refreshing this exact project — don't start a second, conflicting call.
      return;
    }
    const targetName = selectedProject?.name;
    setProjectBusyFlag(targetId, "refreshing", true);
    if (targetId === selectedIdRef.current) {
      setDetailError(null);
    }
    try {
      const data = await refreshProjectResume(targetId);
      const history = await fetchProjectHistory(targetId, { force: true });
      setProjectPatches((prev) => {
        const base = bootstrap?.projects.find((p) => p.id === data.project.id);
        return {
          ...prev,
          [data.project.id]: mergeDashboardProject(base, data.project),
        };
      });
      setDetailCache((prev) => ({
        ...prev,
        [targetId]: {
          project: data.project,
          resume_panel: data.resume_panel,
          history,
        },
      }));
      // historyRows describes the currently-displayed project — a refresh
      // that finishes after the user has switched away must not overwrite it (C2).
      if (targetId === selectedIdRef.current) {
        setHistoryRows(history);
        setActionNotice("Project context updated.");
      } else {
        setActionNotice(`Context updated for ${targetName ?? "project"}.`);
      }
    } catch (err) {
      if (targetId === selectedIdRef.current) {
        setDetailError(getUserErrorMessage(err));
      } else {
        setActionNotice(getUserErrorMessage(err));
      }
    } finally {
      setProjectBusyFlag(targetId, "refreshing", false);
    }
  }, [selectedId, selectedProject, bootstrap?.projects, projectBusy, setProjectBusyFlag]);

  // Import context: pick a handoff file -> validated preview -> explicit confirmation.
  // Nothing is written until the user confirms in the dialog.
  const handleImportContext = useCallback(async () => {
    const targetId = selectedId;
    if (targetId === null) return;
    setActionNotice(null);
    try {
      const picked = await openFileDialog({
        title: "Choose a handoff file",
        multiple: false,
        directory: false,
        filters: [{ name: "Handoff (JSON)", extensions: ["json"] }],
      });
      if (typeof picked !== "string") return;
      const preview = await previewContextImport(targetId, picked);
      setImportError(null);
      setImportState({
        projectId: targetId,
        filePath: picked,
        fileName: picked.split(/[\\/]/).pop() ?? picked,
        preview,
      });
    } catch (err) {
      setActionNotice(getUserErrorMessage(err));
    }
  }, [selectedId]);

  const handleConfirmImport = useCallback(
    async (mode: ContextImportMode) => {
      if (!importState) return;
      setImportBusy(true);
      setImportError(null);
      try {
        await applyContextImport(
          importState.projectId,
          importState.filePath,
          mode,
          importState.preview.fingerprint,
          true
        );
        const { projectId, preview } = importState;
        setImportState(null);
        setActionNotice(`Imported context into the notes of ${preview.project_name}.`);
        void loadDetail(projectId, true);
      } catch (err) {
        setImportError(getUserErrorMessage(err));
      } finally {
        setImportBusy(false);
      }
    },
    [importState, loadDetail]
  );

  const handleExport = useCallback(
    async (format: ExportFormat) => {
      const targetId = selectedId;
      if (targetId === null) return;
      if (projectBusy[targetId]?.exporting) {
        return;
      }
      const targetName = selectedProject?.name;
      setProjectBusyFlag(targetId, "exporting", true);
      if (targetId === selectedIdRef.current) {
        setActionNotice(null);
      }
      try {
        const path = await exportProjectToFile(targetId, format);
        setActionNotice(
          targetId === selectedIdRef.current
            ? `Exported to ${path}`
            : `Exported ${targetName ?? "project"} to ${path}`
        );
      } catch (err) {
        if (err instanceof ExportCancelledError) {
          return;
        }
        setActionNotice(getUserErrorMessage(err));
      } finally {
        setProjectBusyFlag(targetId, "exporting", false);
      }
    },
    [selectedId, selectedProject, projectBusy, setProjectBusyFlag]
  );

  useEffect(() => {
    if (selectedId !== null) {
      setDetailError(null);
      setHistoryRows([]);
      setHistoryError(null);
      void loadDetail(selectedId, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh when selection changes only
  }, [selectedId]);

  const loadHistory = useCallback(async (projectId: number) => {
    const seq = ++historyLoadSeq.current;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const rows = await fetchProjectHistory(projectId);
      if (seq !== historyLoadSeq.current) {
        return;
      }
      setHistoryRows(rows);
    } catch (err) {
      if (seq === historyLoadSeq.current) {
        setHistoryError(getUserErrorMessage(err));
      }
    } finally {
      if (seq === historyLoadSeq.current) {
        setHistoryLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (nav === "history" && selectedId !== null) {
      void loadHistory(selectedId);
    }
  }, [nav, selectedId, loadHistory]);

  const detail = selectedId !== null ? detailCache[selectedId] : undefined;
  const resumePanel = detail?.resume_panel ?? null;
  const showWake =
    selectedId !== null &&
    resumePanel &&
    !wakeDismissed[selectedId] &&
    Boolean(
      resumePanel.away_label ??
        resumePanel.startup_summary?.away_label
    );

  const requestRemoveProject = useCallback((project: DashboardProject) => {
    setRemoveTarget(project);
    setRemoveError(null);
    setRemoveDialogOpen(true);
  }, []);

  const handleEditorCloseDetected = useCallback(
    (projectId: number) => {
      if (exitNotePromptedForProjectRef.current === projectId) {
        return;
      }

      if (closeSessionOpenRef.current || closeSessionBusyRef.current) {
        // Another project's exit-note dialog is already open/saving — queue this one
        // instead of dropping it (M10); it's replayed once that dialog closes.
        pendingEditorCloseRef.current.add(projectId);
        return;
      }

      const project = projects.find((item) => item.id === projectId);
      if (!project || !projectHasOpenSession(project)) {
        return;
      }

      exitNotePromptedForProjectRef.current = projectId;
      setCloseSessionProjectId(projectId);
      setCloseSessionError(null);
      setCloseSessionOpen(true);
      void showFromTray().catch(() => {});
    },
    [projects]
  );

  /** Replay one queued editor-close event (if any) now that the dialog is free. */
  const processPendingEditorCloseQueue = useCallback(() => {
    const pending = pendingEditorCloseRef.current;
    const nextId = pending.values().next().value;
    if (nextId === undefined) {
      return;
    }
    pending.delete(nextId);
    handleEditorCloseDetected(nextId);
  }, [handleEditorCloseDetected]);

  const handleCloseSession = async (values: CloseSessionFormValues) => {
    const projectId = closeSessionProjectId ?? selectedId;
    if (!projectId) return;

    setCloseSessionBusy(true);
    setCloseSessionError(null);
    try {
      const result = await withTimeout(
        closeProjectSession(projectId, {
          exit_note: values.exit_note,
          blocker: values.blocker,
          next_step: values.next_step,
          skip_notes: values.skip_notes,
        }),
        CLOSE_SESSION_TIMEOUT_MS,
        "Closing the session did not respond in time."
      );
      setProjectPatches((prev) => {
        const base = bootstrap?.projects.find((p) => p.id === result.project.id);
        return {
          ...prev,
          [result.project.id]: mergeDashboardProject(base, result.project),
        };
      });
      setDetailCache((prev) => ({
        ...prev,
        [projectId]: {
          project: result.project,
          resume_panel: result.resume_panel,
          history: prev[projectId]?.history,
        },
      }));
      setCloseSessionOpen(false);
      setCloseSessionProjectId(null);
      exitNotePromptedForProjectRef.current = null;
      // Scoped to this project only — other projects' lifecycle tracking (H11) must
      // keep running when one project's session is closed.
      stopEditorLifecycleProbe(projectId);
      const notice = result.resume_warning
        ? `${result.message} ${result.resume_warning}`
        : result.message;
      setActionNotice(notice);
      processPendingEditorCloseQueue();
    } catch (err) {
      setCloseSessionError(getUserErrorMessage(err));
    } finally {
      setCloseSessionBusy(false);
    }
  };

  const hideToTrayOnce = useCallback(() => {
    if (hideToTrayCalledRef.current) {
      return;
    }
    hideToTrayCalledRef.current = true;
    void hideToTray().catch(() => {
      setActionNotice("Editor opened. Could not hide the Graf-Id window.");
    });
  }, []);

  useEffect(() => {
    setMainWindowCloseHandler(async () => {
      const context = {
        editorLifecycleActive: isEditorLifecycleProbeActive(),
        hideToTrayUsed: hideToTrayCalledRef.current,
        closeSessionBusy: closeSessionBusyRef.current,
      };

      if (context.closeSessionBusy) {
        return;
      }

      if (resolveMainWindowCloseMode(context) === "hide_tray") {
        hideToTrayOnce();
        return;
      }

      await executeMainWindowClose(context);
    });

    return () => {
      setMainWindowCloseHandler(null);
    };
  }, [hideToTrayOnce]);

  const dismissWakeOverlayOnly = useCallback(() => {
    wakeOverlayDismissedOnlyRef.current = true;
    setWakeTransition((prev) => (prev ? { ...prev, visible: false } : prev));
  }, []);

  const finishWakeSession = useCallback(() => {
    wakeSnapshotRef.current = null;
    launchStartedRef.current = false;
    wakeOverlayDismissedOnlyRef.current = false;
    hideToTrayCalledRef.current = false;
    setWakeTransition(null);
    setOpenProjectBusy(false);
  }, []);

  const runPendingWakePostFadeActions = useCallback(() => {
    const action = postFadeActionRef.current;
    postFadeActionRef.current = null;

    if (action?.type === "hide_tray") {
      hideToTrayOnce();
    } else if (action?.type === "explorer") {
      void (async () => {
        try {
          await openProjectFolderPath(action.projectPath);
          setActionNotice(action.notice);
          await loadDetail(action.projectId, true);
        } catch (err) {
          setActionNotice(getUserErrorMessage(err));
        }
      })();
    } else if (action?.type === "notice_detail") {
      setActionNotice(action.notice);
      void loadDetail(action.projectId, true);
    } else if (action?.type === "error") {
      setActionNotice(action.message);
    }
  }, [hideToTrayOnce, loadDetail]);

  const completeWakeIfOverlayDismissed = useCallback(() => {
    if (!wakeOverlayDismissedOnlyRef.current) {
      return false;
    }
    stopEditorReadinessProbe();
    runPendingWakePostFadeActions();
    finishWakeSession();
    return true;
  }, [finishWakeSession, runPendingWakePostFadeActions]);

  const runProjectWakeLaunch = useCallback(async () => {
    if (launchStartedRef.current) {
      return;
    }
    launchStartedRef.current = true;

    const snapshot = wakeSnapshotRef.current;
    if (!snapshot) {
      launchStartedRef.current = false;
      return;
    }

    setWakeTransition((prev) =>
      prev ? { ...beginProjectWakeLaunch(prev), snapshot: prev.snapshot } : prev
    );

    try {
      const preLaunchEditorCount = await withTimeout(
        capturePreLaunchEditorCount(snapshot.preferredEditor),
        PRE_LAUNCH_PROBE_TIMEOUT_MS,
        "Checking running editors did not respond in time."
      );
      if (!shellMountedRef.current) {
        return;
      }

      const result = await withTimeout(
        openProjectWorkflow(snapshot.projectId),
        OPEN_PROJECT_TIMEOUT_MS,
        "Open Project did not respond in time."
      );
      if (!shellMountedRef.current) {
        return;
      }

      setProjectPatches((prev) => {
        const base = bootstrap?.projects.find((p) => p.id === result.project.id);
        return {
          ...prev,
          [result.project.id]: mergeDashboardProject(base, result.project),
        };
      });

      const launch = result.launch;
      const editorLaunched =
        launch.success !== false &&
        launch.editor_launched &&
        !launch.fallback_used;

      if (!editorLaunched) {
        const notice =
          launch.fallback_used && launch.message
            ? `Warning: ${launch.message}`
            : launch.message;

        if (launch.explorer_opened && !editorLaunched) {
          postFadeActionRef.current = {
            type: "explorer",
            projectPath: snapshot.projectPath,
            notice,
            projectId: snapshot.projectId,
          };
        } else {
          postFadeActionRef.current = {
            type: "notice_detail",
            notice,
            projectId: snapshot.projectId,
          };
        }

        if (completeWakeIfOverlayDismissed()) {
          return;
        }
        setWakeTransition((prev) =>
          prev ? { ...projectWakeLaunchFailed(prev), snapshot: prev.snapshot } : prev
        );
        return;
      }

      setWakeTransition((prev) =>
        prev ? { ...projectWakeLaunchWaiting(prev), snapshot: prev.snapshot } : prev
      );

      startEditorReadinessProbe({
        preLaunchEditorCount,
        launcherPid: launch.editor_pid ?? null,
        editor: launch.editor,
        editorLaunched: true,
        onReady: () => {
          if (!shellMountedRef.current) {
            return;
          }
          stopEditorReadinessProbe();
          exitNotePromptedForProjectRef.current = null;
          startEditorLifecycleProbe({
            editorPid: launch.editor_pid ?? null,
            editor: launch.editor,
            projectId: snapshot.projectId,
            projectPath: snapshot.projectPath,
            onEditorCloseDetected: () => handleEditorCloseDetected(snapshot.projectId),
          });
          hideToTrayOnce();
          if (wakeOverlayDismissedOnlyRef.current) {
            finishWakeSession();
            return;
          }
          postFadeActionRef.current = { type: "hide_tray" };
          setWakeTransition((prev) =>
            prev ? { ...projectWakeEditorReady(prev), snapshot: prev.snapshot } : prev
          );
        },
        onFailure: () => {
          if (!shellMountedRef.current) {
            return;
          }
          stopEditorReadinessProbe();
          postFadeActionRef.current = {
            type: "notice_detail",
            notice: launch.message || "Editor did not start.",
            projectId: snapshot.projectId,
          };
          if (completeWakeIfOverlayDismissed()) {
            return;
          }
          setWakeTransition((prev) =>
            prev ? { ...projectWakeLaunchFailed(prev), snapshot: prev.snapshot } : prev
          );
        },
      });
    } catch (err) {
      if (!shellMountedRef.current) {
        return;
      }
      postFadeActionRef.current = {
        type: "error",
        message: getUserErrorMessage(err),
      };
      if (completeWakeIfOverlayDismissed()) {
        return;
      }
      setWakeTransition((prev) =>
        prev ? { ...projectWakeLaunchFailed(prev), snapshot: prev.snapshot } : prev
      );
    }
  }, [
    bootstrap?.projects,
    completeWakeIfOverlayDismissed,
    finishWakeSession,
    handleEditorCloseDetected,
    hideToTrayOnce,
  ]);

  const handleWakeTransitionHidden = useCallback(() => {
    if (wakeOverlayDismissedOnlyRef.current) {
      return;
    }

    stopEditorReadinessProbe();
    runPendingWakePostFadeActions();
    finishWakeSession();
  }, [finishWakeSession, runPendingWakePostFadeActions]);

  const handleWakeSkip = useCallback(() => {
    if (launchTimerRef.current !== null) {
      window.clearTimeout(launchTimerRef.current);
      launchTimerRef.current = null;
    }

    if (launchStartedRef.current) {
      dismissWakeOverlayOnly();
      return;
    }

    setWakeTransition((prev) =>
      prev ? { ...skipProjectWakeIntro(prev), snapshot: prev.snapshot } : prev
    );

    void runProjectWakeLaunch();
  }, [dismissWakeOverlayOnly, runProjectWakeLaunch]);

  /** Coding Agents (M7): a deliberately separate, minimal launcher path.
   * No wake transition, no work session, no editor lifecycle/readiness
   * probe, no Exit Note — Graf-Id resolves the executable/args/cwd and
   * hands off to a Rust terminal spawn, then stops tracking. */
  const handleOpenProjectWithAgent = useCallback(
    async (agentId: string, projectId: number) => {
      setOpenProjectBusy(true);
      setActionNotice(null);
      setDetailError(null);
      try {
        const spec = await openProjectWithCodingAgent(agentId, projectId);
        setActionNotice(`${spec.display_name} started in ${spec.cwd}`);
      } catch (err) {
        setActionNotice(getUserErrorMessage(err));
      } finally {
        setOpenProjectBusy(false);
      }
    },
    []
  );

  // Open Project: wake transition, then Python workflow + optional Rust Explorer.
  const handleOpenProject = () => {
    if (selectedId === null || !selectedProject || openProjectBusy) return;
    if (selectedProject.path_accessible === false) {
      setActionNotice(
        "Registered folder not found. Restore the path on disk or remove this project from Graf-Id."
      );
      return;
    }

    // Route to the Coding Agent launcher before any editor/session
    // machinery starts (M7/M8): agents never go through the wake overlay,
    // never create a work session, and never get an Exit Note.
    const openerValue =
      selectedProject.preferred_ide ?? effectiveAppSettings?.default_project_opener ?? null;
    const agentId = agentIdFromOpenerValue(openerValue);
    if (agentId !== null) {
      void handleOpenProjectWithAgent(agentId, selectedId);
      return;
    }

    const snapshot: ProjectWakeSnapshot = {
      projectId: selectedId,
      projectName: selectedProject.name,
      projectPath: selectedProject.path,
      preferredEditor: selectedProject.preferred_ide ?? null,
    };
    const reducedMotion = prefersReducedMotion();

    if (launchTimerRef.current !== null) {
      window.clearTimeout(launchTimerRef.current);
      launchTimerRef.current = null;
    }

    wakeSnapshotRef.current = snapshot;
    postFadeActionRef.current = null;
    launchStartedRef.current = false;
    wakeOverlayDismissedOnlyRef.current = false;
    hideToTrayCalledRef.current = false;

    setOpenProjectBusy(true);
    setActionNotice(null);
    setDetailError(null);
    setWakeTransition({
      ...createProjectWakeUiState(reducedMotion),
      snapshot,
    });

    const launchDelayMs = getProjectWakeLaunchDelayMs(reducedMotion);
    launchTimerRef.current = window.setTimeout(() => {
      launchTimerRef.current = null;
      void runProjectWakeLaunch();
    }, launchDelayMs);
  };

  const handleProjectAdded = (project: DashboardProject, message: string) => {
    onProjectAdded(project);
    setProjectPatches((prev) => {
      const base = bootstrap?.projects.find((p) => p.id === project.id);
      return {
        ...prev,
        [project.id]: mergeDashboardProject(base, project),
      };
    });
    setSelectedId(project.id);
    setNav("dashboard");
    setActionNotice(message);
    void loadDetail(project.id, true);
  };

  const handleRemoveProject = async () => {
    if (!removeTarget) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      const result = await removeProject(removeTarget.id);
      const removedId = removeTarget.id;
      onProjectRemoved(removedId);
      setProjectPatches((prev) => {
        const next = { ...prev };
        delete next[removedId];
        return next;
      });
      setDetailCache((prev) => {
        const next = { ...prev };
        delete next[removedId];
        return next;
      });
      const remaining = projects.filter((p) => p.id !== removedId);
      const nextSelected = sortProjectsForSidebar(remaining)[0]?.id ?? null;
      setSelectedId(nextSelected);
      setRemoveDialogOpen(false);
      setRemoveTarget(null);
      setActionNotice(result.message);
    } catch (err) {
      setRemoveError(getUserErrorMessage(err));
    } finally {
      setRemoveBusy(false);
    }
  };

  const handleReorderProjects = useCallback(
    async (orderedIds: number[]) => {
      // No caller catches a rethrow here (ProjectDashboard's handleDrop only has a
      // `finally`), so it would surface as an unhandled rejection for no benefit (L8).
      try {
        const result = await reorderProjects(orderedIds);
        onProjectsReordered(result.projects);
      } catch (err) {
        setActionNotice(getUserErrorMessage(err));
      }
    },
    [onProjectsReordered]
  );

  const handleGrafiOpenSummary = useCallback(() => {
    setNav("dashboard");
    if (selectedId !== null) {
      setWakeDismissed((prev) => ({ ...prev, [selectedId]: true }));
      requestAnimationFrame(() => {
        document.getElementById("resume-panel-primary")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    }
  }, [selectedId]);

  const grafiDetailReady =
    selectedId !== null && Boolean(detailCache[selectedId]) && !detailLoading;
  const selectedBusy = selectedId !== null ? projectBusy[selectedId] : undefined;

  return (
    <GrafiHelpProvider>
    <div className={`app-shell${!hasProjects ? " app-shell--no-projects" : ""}`}>
      <header className="app-shell__titlebar">
        <div className="app-shell__brand">
          <img
            className="app-shell__logo-mark"
            src={grafIdLogo}
            alt=""
            aria-hidden="true"
            draggable={false}
          />
          <span className="app-shell__logo">Graf-Id</span>
        </div>
        <span className="app-shell__tag">Local workflow continuity · Passive runtime</span>
      </header>
      <div className="app-shell__body">
        <NavSidebar
          section={nav}
          onNav={setNav}
          hasProjects={hasProjects}
          projects={projects}
          selectedId={selectedId}
          onSelectProject={setSelectedId}
          onAddProject={() => setAddProjectOpen(true)}
          onRemoveProject={requestRemoveProject}
          onReorderProjects={handleReorderProjects}
        />
        <main className="app-shell__main">
          {!hasProjects && nav === "dashboard" ? (
            <EmptyState
              title="No projects yet"
              message="Register a project folder to start tracking where you left off. Graf-Id remembers sessions, scans, and resume context for registered projects."
              dataFolder={bootstrap?.config_dir}
              hint="Add a project folder to get started. Use Open project to launch your editor."
              onAddProject={() => setAddProjectOpen(true)}
            />
          ) : null}

          {actionNotice ? (
            <p className="app-shell__notice" role="status">
              {actionNotice}
            </p>
          ) : null}

          {hasProjects && nav === "dashboard" ? (
            selectedProject ? (
              <section className="project-detail">
                <ProjectDetailHeader
                  project={selectedProject}
                  refreshing={Boolean(selectedBusy?.refreshing)}
                  exportBusy={Boolean(selectedBusy?.exporting)}
                  openProjectBusy={openProjectBusy}
                  onRefreshResume={
                    selectedId !== null ? () => void handleRefreshResume() : undefined
                  }
                  onExport={
                    selectedId !== null ? (format) => void handleExport(format) : undefined
                  }
                  onImportContext={
                    selectedId !== null ? () => void handleImportContext() : undefined
                  }
                  onOpenProject={() => void handleOpenProject()}
                />

                {showWake && resumePanel ? (
                  <WakePanel
                    panel={resumePanel}
                    onContinue={() =>
                      setWakeDismissed((prev) => ({
                        ...prev,
                        [selectedId!]: true,
                      }))
                    }
                  />
                ) : null}

                <ResumePanel
                  panel={resumePanel}
                  loading={detailLoading && !detail}
                  error={detailError}
                  onRetry={
                    selectedId !== null
                      ? () => void loadDetail(selectedId, true)
                      : undefined
                  }
                />

                <BuildCacheCard
                  projectId={selectedProject.id}
                  projectPath={selectedProject.path}
                />
              </section>
            ) : (
              <EmptyState
                title="Select a project"
                message="Choose a project from the sidebar to view resume context and continue where you left off."
              />
            )
          ) : null}

          {hasProjects && nav === "history" ? (
            <HistorySection
              project={selectedProject}
              rows={historyRows}
              loading={historyLoading}
              error={historyError}
              onRetry={
                selectedId !== null ? () => void loadHistory(selectedId) : undefined
              }
            />
          ) : null}

          {nav === "settings" ? <Settings onSettingsSaved={setAppSettingsOverride} /> : null}
        </main>
      </div>

      <AddProjectDialog
        open={addProjectOpen}
        onClose={() => setAddProjectOpen(false)}
        onAdded={handleProjectAdded}
      />

      {importState ? (
        <ImportContextDialog
          preview={importState.preview}
          fileName={importState.fileName}
          busy={importBusy}
          error={importError}
          onConfirm={(mode) => void handleConfirmImport(mode)}
          onCancel={() => {
            if (!importBusy) {
              setImportState(null);
              setImportError(null);
            }
          }}
        />
      ) : null}

      {removeTarget ? (
        <RemoveProjectDialog
          open={removeDialogOpen}
          projectName={removeTarget.name}
          removing={removeBusy}
          error={removeError}
          onConfirm={() => void handleRemoveProject()}
          onCancel={() => {
            if (!removeBusy) {
              setRemoveDialogOpen(false);
              setRemoveTarget(null);
              setRemoveError(null);
            }
          }}
        />
      ) : null}

      {wakeTransition?.active ? (
        <ProjectWakeTransition
          projectName={wakeTransition.snapshot.projectName}
          visible={wakeTransition.visible}
          revealAllLines={wakeTransition.revealAllLines}
          waitingForEditor={wakeTransition.waitingForEditor}
          loopAnimation={wakeTransition.loopAnimation}
          onSkip={handleWakeSkip}
          onHidden={handleWakeTransitionHidden}
        />
      ) : null}

      {closeSessionOpen && closeSessionProjectId !== null ? (
        <CloseSessionDialog
          open={closeSessionOpen}
          projectName={
            projects.find((item) => item.id === closeSessionProjectId)?.name ??
            selectedProject?.name ??
            "Project"
          }
          closing={closeSessionBusy}
          error={closeSessionError}
          onSubmit={(values) => void handleCloseSession(values)}
        />
      ) : null}

      <GrafiAdvisorHost
        nav={nav}
        project={selectedProject}
        panel={detail?.resume_panel ?? null}
        projectSelected={selectedId !== null}
        detailReady={grafiDetailReady}
        detailError={detailError}
        onOpenSummary={handleGrafiOpenSummary}
      />
    </div>
    </GrafiHelpProvider>
  );
}
