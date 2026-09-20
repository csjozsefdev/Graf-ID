import type { ResumePanelData } from "../ipc/types";

interface WakePanelProps {
  panel: ResumePanelData;
  onContinue: () => void;
}

/** Short "before you continue" screen after a long absence. */
export function WakePanel({ panel, onContinue }: WakePanelProps) {
  const summary = panel.startup_summary;
  if (!summary) return null;

  const away = summary.away_label ?? panel.away_label;
  if (!away) return null;

  return (
    <section className="wake-panel" aria-label="Before you continue">
      <h3>Before you continue</h3>
      <p className="wake-panel__away">{away}</p>
      {summary.headline ? <p className="wake-panel__headline">{summary.headline}</p> : null}
      {summary.mvp_sections && summary.mvp_sections.length > 0 ? (
        <ul className="wake-panel__sections">
          {summary.mvp_sections.slice(0, 3).map((section, index) => (
            <li key={`${section.title}-${index}`}>
              <strong>{section.title}</strong>
              <span>{section.body}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{summary.summary_text}</p>
      )}
      <button type="button" className="startup__button" onClick={onContinue}>
        Continue to project
      </button>
    </section>
  );
}
