import type { ProjectSnapshot } from "../ipc/types";
import { snapshotSubsections } from "../utils/projectSnapshot";

interface ProjectSnapshotCardProps {
  snapshot: ProjectSnapshot | null | undefined;
}

/** Quick-glance Project Snapshot under "Where you left off". Renders nothing when empty. */
export function ProjectSnapshotCard({ snapshot }: ProjectSnapshotCardProps) {
  const sections = snapshotSubsections(snapshot);
  if (sections.length === 0) {
    return null;
  }

  return (
    <div
      className="resume-panel__block resume-panel__block--primary resume-panel__snapshot"
      aria-label="Project Snapshot"
    >
      <h4>Project Snapshot</h4>
      {sections.map((section) => (
        <div key={section.key} className="resume-panel__snapshot-section">
          <h5>{section.title}</h5>
          {section.items.length === 1 && section.key !== "open_issues" ? (
            <p className="resume-panel__answer resume-panel__section-body">{section.items[0]}</p>
          ) : (
            <ul className="resume-panel__snapshot-list">
              {section.items.map((item) => (
                <li key={`${section.key}-${item}`}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
