import type { DashboardProject, HistoryRow } from "../ipc/types";

import { EmptyState } from "./EmptyState";

interface HistorySectionProps {
  project: DashboardProject | null;
  rows: HistoryRow[];
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}

function HistoryCard({ row }: { row: HistoryRow }) {
  const changedFiles =
    row.changed_files_count != null ? String(row.changed_files_count) : "—";

  return (
    <article className="history-card" aria-label={`Scan on ${row.scanned_at_label}`}>
      <dl className="history-card__fields">
        <div className="history-card__field">
          <dt>Project</dt>
          <dd>{row.project_name || "—"}</dd>
        </div>
        <div className="history-card__field">
          <dt>Date</dt>
          <dd>{row.scanned_at_label || "Unknown date"}</dd>
        </div>
        <div className="history-card__field history-card__field--summary">
          <dt>Summary</dt>
          <dd className="history-card__summary">
            {row.summary_preview || "No summary available"}
          </dd>
        </div>
        <div className="history-card__field">
          <dt>Changed files</dt>
          <dd>{changedFiles}</dd>
        </div>
        {row.session_duration_label ? (
          <div className="history-card__field">
            <dt>Duration</dt>
            <dd>{row.session_duration_label}</dd>
          </div>
        ) : null}
      </dl>
      <p className="history-card__meta muted">
        Scan snapshot
        {row.summary_source === "session_best_effort" ? " · session linked (best effort)" : ""}
        {" · #"}
        {row.snapshot_id}
      </p>
    </article>
  );
}

export function HistorySection({
  project,
  rows,
  loading,
  error,
  onRetry,
}: HistorySectionProps) {
  if (!project) {
    return (
      <EmptyState
        title="History"
        message="Select a project from the dashboard to view scan history."
      />
    );
  }

  return (
    <section className="history-section" aria-label="Scan history">
      <h2>History — {project.name}</h2>
      <p className="muted">
        Scan snapshots from the local database. Session notes are matched best-effort when
        available.
      </p>

      {loading ? (
        <div className="panel-loading" aria-busy="true">
          <span className="panel-loading__spinner" aria-hidden="true" />
          <p className="muted">Loading history…</p>
        </div>
      ) : null}

      {error ? (
        <div className="history-section__error">
          <p className="error-text">{error}</p>
          {onRetry ? (
            <button type="button" className="startup__button" onClick={onRetry}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}

      {!loading && !error && rows.length === 0 ? (
        <EmptyState
          title="No scans yet"
          message="Use Refresh context on the dashboard to capture a scan snapshot for this project."
        />
      ) : null}

      {!loading && !error && rows.length === 1 ? (
        <p className="history-section__intro muted">
          One snapshot on record. Refresh context to build a longer timeline.
        </p>
      ) : null}

      {!loading && !error && rows.length > 0 ? (
        <div className="history-section__list">
          {rows.map((row) => (
            <HistoryCard key={row.snapshot_id} row={row} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
