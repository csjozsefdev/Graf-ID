import type { MvpSection, ProjectSnapshot } from "../ipc/types";

export interface SnapshotSubsection {
  key: keyof ProjectSnapshot;
  title: string;
  items: string[];
}

const SUBSECTIONS: Array<{ key: keyof ProjectSnapshot; title: string }> = [
  { key: "current_focus", title: "Current focus" },
  { key: "open_issues", title: "Open issues / blockers" },
  { key: "recent_fixes", title: "Recent fixes" },
  { key: "recent_improvements", title: "Recent improvements" },
  { key: "suggested_next_step", title: "Suggested next step" },
];

function clean(items: unknown): string[] {
  if (typeof items === "string") {
    return items.trim() ? [items.trim()] : [];
  }
  return Array.isArray(items)
    ? items.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];
}

/** Only sections that have reliable content — empty ones never render. */
export function snapshotSubsections(
  snapshot: ProjectSnapshot | null | undefined
): SnapshotSubsection[] {
  if (!snapshot) return [];
  return SUBSECTIONS.map(({ key, title }) => ({ key, title, items: clean(snapshot[key]) })).filter(
    (section) => section.items.length > 0
  );
}

export function hasProjectSnapshot(snapshot: ProjectSnapshot | null | undefined): boolean {
  return snapshotSubsections(snapshot).length > 0;
}

/** MVP-section stand-ins for what the snapshot already shows, so the panel never repeats it. */
export function snapshotCoveredSections(
  snapshot: ProjectSnapshot | null | undefined
): MvpSection[] {
  const covered: MvpSection[] = [];
  for (const step of clean(snapshot?.suggested_next_step)) {
    covered.push({ title: "Suggested next step", body: step });
  }
  for (const issue of clean(snapshot?.open_issues)) {
    covered.push({ title: "Blocker", body: issue });
  }
  return covered;
}
