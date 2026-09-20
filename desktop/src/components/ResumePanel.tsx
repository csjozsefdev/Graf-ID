import type { HTMLAttributes, ReactNode } from "react";
import type { ResumePanelData } from "../ipc/types";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";
import {
  formatTimeSince,
  formatWhen,
  hasText,
  isStaleProject,
  recommendedAction,
} from "../utils/continuity";
import { layoutResumeSections, sessionFieldsDuplicatedInSections } from "../utils/resumeSections";
import { hasProjectSnapshot, snapshotCoveredSections } from "../utils/projectSnapshot";
import { ProjectSnapshotCard } from "./ProjectSnapshotCard";
import {
  gitContextLabel,
  scanContextLabel,
  sessionContextLabel,
  taskMarkerLabel,
} from "../utils/selectedProjectCard";

interface ResumePanelProps {
  panel: ResumePanelData | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

function ContextBlock({
  title,
  children,
  tone = "default",
  ...rest
}: {
  title: string;
  children: ReactNode;
  tone?: "default" | "primary" | "supporting";
} & HTMLAttributes<HTMLDivElement>) {
  const toneClass =
    tone === "primary"
      ? " resume-panel__block--primary"
      : tone === "supporting"
        ? " resume-panel__block--supporting"
        : "";

  return (
    <div className={`resume-panel__block${toneClass}`} {...rest}>
      <h4>{title}</h4>
      {children}
    </div>
  );
}

function FieldRow({
  label,
  value,
  empty,
}: {
  label: string;
  value: string | null;
  empty: string;
}) {
  return (
    <div>
      <span className="label">{label}</span>
      <p>{value ?? <span className="muted">{empty}</span>}</p>
    </div>
  );
}

export function ResumePanel({
  panel,
  loading,
  error,
  onRetry,
}: ResumePanelProps) {
  if (loading) {
    return (
      <section className="resume-panel" aria-label="Resume context" aria-busy="true">
        <div className="panel-loading">
          <span className="panel-loading__spinner" aria-hidden="true" />
          <p className="muted">Loading…</p>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="resume-panel resume-panel--error" aria-label="Resume context">
        <p className="error-text">{error}</p>
        {onRetry ? (
          <button type="button" className="startup__button" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </section>
    );
  }

  if (!panel) {
    return (
      <section className="resume-panel" aria-label="Resume context">
        <p className="muted">No resume context loaded for this project.</p>
      </section>
    );
  }

  const neverScanned = !panel.has_stored_resume && !panel.latest_scan_at;

  const blocker = hasText(panel.blocker) ? panel.blocker!.trim() : null;
  const nextStep = hasText(panel.next_step) ? panel.next_step!.trim() : null;
  const exitNote = hasText(panel.exit_note) ? panel.exit_note!.trim() : null;
  const session = panel.latest_session;
  const startup = panel.startup_summary;
  const humanContext =
    (startup?.source === "human_context" || startup?.source === "summary_engine") &&
    hasText(startup.summary_text);
  const action = humanContext
    ? startup!.summary_text!.trim()
    : recommendedAction({
        next_step: nextStep,
        blocker,
        exit_note: exitNote,
        has_unfinished_session: session?.is_active,
      });
  const stale = isStaleProject(panel.last_opened_at);
  const git = panel.git_status;
  const timeline = panel.timeline ?? startup?.timeline ?? [];
  const mvpSections = startup?.mvp_sections ?? [];
  const snapshot = panel.project_snapshot ?? startup?.project_snapshot ?? null;
  const snapshotVisible = hasProjectSnapshot(snapshot);
  const snapshotCovered = snapshotCoveredSections(snapshot);
  const { whereLeftOff, lead, evidence } = layoutResumeSections(mvpSections, snapshotCovered);
  const primarySections = [...(whereLeftOff ? [whereLeftOff] : []), ...lead];
  const sessionFieldVisibility = sessionFieldsDuplicatedInSections(
    [...primarySections, ...snapshotCovered],
    {
      blocker,
      nextStep,
      exitNote,
    }
  );
  const showSessionGrid =
    (sessionFieldVisibility.showBlocker && blocker) ||
    (sessionFieldVisibility.showNextStep && nextStep) ||
    (sessionFieldVisibility.showExitNote && exitNote);

  return (
    <section className="resume-panel resume-panel--calm" aria-label="Resume context">
      <div className="resume-panel__alerts">
        {stale ? (
          <p className="resume-panel__stale">
            This project has not been opened in over two weeks.
          </p>
        ) : null}
        {session?.is_active && !humanContext ? (
          <p className="resume-panel__active">Session is still open.</p>
        ) : null}
      </div>

      <div
        className="resume-panel__primary-zone"
        id="resume-panel-primary"
        {...grafiHelpProps(GRAFI_HELP_TOPIC.RESUME_SUMMARY)}
      >
        {neverScanned && primarySections.length === 0 && !snapshotVisible && !humanContext ? (
          <ContextBlock title="No scan yet" tone="primary">
            <p className="resume-panel__answer resume-panel__section-body--lead">
              Use Refresh context to capture a scan snapshot for this project.
            </p>
          </ContextBlock>
        ) : null}

        {whereLeftOff ? (
          <ContextBlock title={whereLeftOff.title} tone="primary">
            <p className="resume-panel__answer resume-panel__section-body resume-panel__section-body--lead">
              {whereLeftOff.body}
            </p>
          </ContextBlock>
        ) : null}

        <ProjectSnapshotCard snapshot={snapshot} />

        {lead.map((section, index) => (
          <ContextBlock key={`${section.title}-${index}`} title={section.title} tone="supporting">
            <p className="resume-panel__answer resume-panel__section-body">{section.body}</p>
          </ContextBlock>
        ))}

        {!whereLeftOff && lead.length === 0 && !snapshotVisible && (!neverScanned || humanContext) ? (
          <ContextBlock title={humanContext ? "Context" : "Recommended next"} tone="primary">
            <p className="resume-panel__answer resume-panel__section-body--lead">{action}</p>
            {humanContext && panel.sources_used && panel.sources_used.length > 0 ? (
              <p className="muted resume-panel__sources">
                Sources: {panel.sources_used.join(", ")}
              </p>
            ) : null}
          </ContextBlock>
        ) : null}

        {evidence.length > 0 ? (
          <details className="resume-panel__fold resume-panel__evidence">
            <summary>Evidence &amp; details</summary>
            <div className="resume-panel__fold-body">
              {evidence.map((section, index) => (
                <ContextBlock
                  key={`${section.title}-${index}`}
                  title={section.title}
                  tone="supporting"
                >
                  <p className="resume-panel__section-body resume-panel__section-body--metadata">
                    {section.body}
                  </p>
                </ContextBlock>
              ))}
            </div>
          </details>
        ) : null}

        {showSessionGrid ? (
          <div className="resume-panel__grid resume-panel__grid--compact resume-panel__block--supporting">
            {sessionFieldVisibility.showBlocker ? (
              <FieldRow label="Blocker" value={blocker} empty="No blocker recorded." />
            ) : null}
            {sessionFieldVisibility.showNextStep ? (
              <FieldRow label="Next step" value={nextStep} empty="No next step recorded." />
            ) : null}
            {sessionFieldVisibility.showExitNote ? (
              <div {...grafiHelpProps(GRAFI_HELP_TOPIC.EXIT_NOTE)}>
                <FieldRow
                  label="Last completed"
                  value={exitNote}
                  empty="No exit note recorded yet."
                />
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <details className="resume-panel__fold">
        <summary>Activity &amp; sources</summary>
        <div className="resume-panel__fold-body">
          <div className="resume-panel__meta">
            <p className="muted">
              Last opened: {formatWhen(panel.last_opened_at)}
              {formatTimeSince(panel.last_opened_at)
                ? ` (${formatTimeSince(panel.last_opened_at)})`
                : ""}
            </p>
            {session ? (
              <p className="muted">
                {sessionContextLabel(session)}
                {!session.is_active && session.ended_at
                  ? ` — ended ${formatWhen(session.ended_at)}`
                  : ""}
              </p>
            ) : (
              <p className="muted">{sessionContextLabel(session)}</p>
            )}
            <p className="muted">
              {panel.latest_scan_at
                ? `Latest scan: ${formatWhen(panel.latest_scan_at)}${
                    formatTimeSince(panel.latest_scan_at)
                      ? ` (${formatTimeSince(panel.latest_scan_at)})`
                      : ""
                  }`
                : scanContextLabel(panel.latest_scan_at)}
            </p>
            {panel.last_refreshed_at ? (
              <p className="muted">
                Last refreshed: {formatWhen(panel.last_refreshed_at)}
                {formatTimeSince(panel.last_refreshed_at)
                  ? ` (${formatTimeSince(panel.last_refreshed_at)})`
                  : ""}
              </p>
            ) : null}
          </div>

          {timeline.length > 0 ? (
            <ContextBlock title="Recent sessions" tone="supporting">
              <ul className="resume-panel__timeline">
                {timeline.map((entry) => (
                  <li key={entry.session_id}>
                    <span className="resume-panel__timeline-when">
                      {formatWhen(entry.ended_at ?? entry.started_at)}
                    </span>
                    {entry.duration_label ? (
                      <span className="muted"> · {entry.duration_label}</span>
                    ) : null}
                    {entry.exit_note_preview ? (
                      <p className="resume-panel__timeline-note">{entry.exit_note_preview}</p>
                    ) : (
                      <p className="muted">No exit note</p>
                    )}
                  </li>
                ))}
              </ul>
            </ContextBlock>
          ) : null}

          {panel.attributed_lines && panel.attributed_lines.length > 0 ? (
            <ContextBlock title="Context (sources)" tone="supporting">
              <ul className="resume-panel__attributed">
                {panel.attributed_lines.map((line) => (
                  <li key={`${line.source}-${line.text}`}>
                    <span className="resume-panel__source-tag">[{line.source}]</span> {line.text}
                  </li>
                ))}
              </ul>
            </ContextBlock>
          ) : null}

          {startup && hasText(startup.headline) && !humanContext ? (
            <ContextBlock title="Workflow context" tone="supporting">
              <p className="resume-panel__headline">{startup.headline}</p>
              {panel.sources_used && panel.sources_used.length > 0 ? (
                <p className="muted">Sources: {panel.sources_used.join(", ")}</p>
              ) : null}
              {startup.generated_at ? (
                <p className="muted">
                  Summary generated {formatWhen(startup.generated_at)}
                  {formatTimeSince(startup.generated_at)
                    ? ` (${formatTimeSince(startup.generated_at)})`
                    : ""}
                </p>
              ) : null}
            </ContextBlock>
          ) : null}
        </div>
      </details>

      <details className="resume-panel__fold">
        <summary>Scan &amp; git detail</summary>
        <div className="resume-panel__fold-body">
          <ContextBlock title="Git" tone="supporting">
            <p>{gitContextLabel(git)}</p>
          </ContextBlock>

          <ContextBlock title="Task markers" tone="supporting">
            <p className="muted">{taskMarkerLabel(panel.open_task_count)}</p>
          </ContextBlock>

          {(panel.modified_files ?? []).length > 0 ? (
            <ContextBlock
              title="Modified files (last scan)"
              tone="supporting"
              {...grafiHelpProps(GRAFI_HELP_TOPIC.MODIFIED_FILES)}
            >
              <ul className="resume-panel__files">
                {(panel.modified_files ?? []).slice(0, 5).map((file) => (
                  <li key={file}>{file}</li>
                ))}
              </ul>
              {(panel.modified_files ?? []).length > 5 ? (
                <p className="muted">+{(panel.modified_files ?? []).length - 5} more</p>
              ) : null}
            </ContextBlock>
          ) : git.is_git_repo ? (
            <p className="muted">No modified files recorded at last scan.</p>
          ) : null}

          {panel.stored_resume_excerpt ? (
            <details className="resume-panel__details">
              <summary>Stored resume excerpt</summary>
              <pre className="resume-panel__excerpt">{panel.stored_resume_excerpt}</pre>
            </details>
          ) : !panel.has_stored_resume && !humanContext && primarySections.length === 0 ? (
            <p className="muted">
              No saved resume details yet. Use Refresh context to build a summary.
            </p>
          ) : null}
        </div>
      </details>
    </section>
  );
}
