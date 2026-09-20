export function scanContextLabel(latestScanAt: string | null | undefined): string {
  if (!latestScanAt) {
    return "No scan has been run for this project yet.";
  }
  return "Latest scan recorded.";
}

export function taskMarkerLabel(count: number | null | undefined): string {
  if (count === null || count === undefined) {
    return "Use Refresh context to scan the project and update TODO/FIXME data.";
  }
  if (count === 0) {
    return "No open TODO/FIXME markers in the latest scan.";
  }
  return `${count} open TODO/FIXME marker${count === 1 ? "" : "s"} in the latest scan.`;
}

export function gitContextLabel(
  git: { state: string; label: string; branch: string | null } | undefined
): string {
  if (!git || git.state === "unknown") {
    return "No git information from the latest scan.";
  }
  return git.branch ? `${git.label} — branch ${git.branch}` : git.label;
}

export function sessionContextLabel(
  session: { is_active: boolean; ended_at: string | null } | null | undefined
): string {
  if (!session) {
    return "No work session recorded yet.";
  }
  if (session.is_active) {
    return "Session is still open.";
  }
  return "Last session has ended.";
}
