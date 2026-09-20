import type { ExportFormat } from "../ipc/client";
import type { DashboardProject } from "../ipc/types";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";
import { formatTimeSince, formatWhen, isStaleProject } from "../utils/continuity";
import { statusLabel } from "../utils/projectStatus";
import { taskMarkerLabel } from "../utils/selectedProjectCard";

function formatCompactPath(path: string): string {
  const trimmed = path.trim();
  if (trimmed.length <= 56) {
    return trimmed;
  }
  const parts = trimmed.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length >= 2) {
    const tail = parts.slice(-2).join("/");
    if (tail.length <= 52) {
      return `…/${tail}`;
    }
  }
  return `…${trimmed.slice(-52)}`;
}

function sessionStateLabel(project: DashboardProject): string {
  const session = project.latest_session;
  if (!session) {
    return "None yet";
  }
  return session.is_active ? "Still open" : "Ended";
}

interface ProjectDetailHeaderProps {
  project: DashboardProject;
  refreshing?: boolean;
  exportBusy?: boolean;
  openProjectBusy?: boolean;
  onRefreshResume?: () => void;
  onExport?: (format: ExportFormat) => void;
  onImportContext?: () => void;
  onOpenProject?: () => void;
}

export function ProjectDetailHeader({
  project,
  refreshing = false,
  exportBusy = false,
  openProjectBusy = false,
  onRefreshResume,
  onExport,
  onImportContext,
  onOpenProject,
}: ProjectDetailHeaderProps) {
  const stale = isStaleProject(project.last_opened_at);
  const folderMissing = project.path_accessible === false;
  const session = project.latest_session;
  const git = project.git_status;
  const actionsDisabled = refreshing || exportBusy || openProjectBusy;
  const pathActionsDisabled = actionsDisabled || folderMissing;

  return (
    <header className="project-detail__header">
      <div className="project-detail__top">
        <div className="project-detail__intro">
          <h2 title={project.name}>{project.name}</h2>
          <p className="muted project-detail__path-short" title={project.path}>
            {formatCompactPath(project.path)}
          </p>
          {folderMissing ? (
            <p className="project-detail__path-missing" role="status">
              Registered folder not found. Restore the path on disk or remove this project
              from Graf-Id.
            </p>
          ) : null}
          {onOpenProject ? (
            <button
              type="button"
              className="project-detail__open-project"
              disabled={pathActionsDisabled}
              onClick={onOpenProject}
              {...grafiHelpProps(GRAFI_HELP_TOPIC.OPEN_PROJECT)}
            >
              {openProjectBusy ? "Opening…" : "Open project"}
            </button>
          ) : null}
        </div>

        <div className="project-detail__header-actions">
          {onExport ? (
            <div
              className="project-detail__export-group"
              role="group"
              aria-label="Export summary"
              {...grafiHelpProps(GRAFI_HELP_TOPIC.EXPORT)}
            >
              <button
                type="button"
                className="project-detail__export project-detail__export--secondary"
                disabled={actionsDisabled}
                title="Lean JSON that GrafiTalk imports directly"
                onClick={() => onExport("handoff")}
              >
                GrafiTalk handoff
              </button>
              <button
                type="button"
                className="project-detail__export project-detail__export--secondary"
                disabled={actionsDisabled}
                title="Full project context as JSON"
                onClick={() => onExport("json")}
              >
                JSON
              </button>
              <button
                type="button"
                className="project-detail__export project-detail__export--secondary"
                disabled={actionsDisabled}
                onClick={() => onExport("markdown")}
              >
                Markdown
              </button>
              <button
                type="button"
                className="project-detail__export project-detail__export--secondary"
                disabled={actionsDisabled}
                onClick={() => onExport("txt")}
              >
                TXT
              </button>
            </div>
          ) : null}
          {onImportContext ? (
            <button
              type="button"
              className="project-detail__export project-detail__export--secondary"
              disabled={actionsDisabled}
              title="Import a handoff file into this project's notes (you review it first)"
              onClick={onImportContext}
            >
              Import context…
            </button>
          ) : null}
          {onRefreshResume ? (
            <button
              type="button"
              className="startup__button project-detail__refresh"
              onClick={onRefreshResume}
              disabled={pathActionsDisabled}
              {...grafiHelpProps(GRAFI_HELP_TOPIC.REFRESH_CONTEXT)}
            >
              {refreshing ? "Refreshing…" : "Refresh context"}
            </button>
          ) : null}
        </div>
      </div>

      <details className="project-detail__more">
        <summary className="project-detail__more-summary">More details</summary>
        <div className="project-detail__more-body">
          {stale ? (
            <p className="project-detail__stale">
              This project has not been opened in over two weeks.
            </p>
          ) : null}

          <dl className="project-detail__facts">
            <div>
              <dt>Path</dt>
              <dd>{project.path}</dd>
            </div>
            <div>
              <dt>Last opened</dt>
              <dd>
                {formatWhen(project.last_opened_at)}
                {formatTimeSince(project.last_opened_at)
                  ? ` (${formatTimeSince(project.last_opened_at)})`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Session</dt>
              <dd>
                {sessionStateLabel(project)}
                {session?.started_at ? ` — started ${formatWhen(session.started_at)}` : ""}
                {session && !session.is_active && session.ended_at
                  ? ` — ended ${formatWhen(session.ended_at)}`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Git</dt>
              <dd>
                <span className={`badge badge--git badge--${git?.state ?? "unknown"}`}>
                  {git?.label ?? "Unknown"}
                  {git?.branch ? ` (${git.branch})` : ""}
                </span>
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <span className="project-detail__status-badge">
                  {statusLabel(project.status ?? "active")}
                </span>
              </dd>
            </div>
            <div>
              <dt>Task markers</dt>
              <dd>{taskMarkerLabel(project.open_task_count)}</dd>
            </div>
          </dl>
        </div>
      </details>
    </header>
  );
}
