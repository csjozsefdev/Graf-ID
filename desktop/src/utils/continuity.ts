/** Deterministic continuity formatting helpers (English-only). */

export function hasText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim());
}

/** Local wall-clock time for a stored (UTC) ISO timestamp — not a raw string slice. */
export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Never";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

export function formatTimeSince(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const diffMs = Date.now() - then.getTime();
  if (diffMs < 0) return "just now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 14) return `${days} day${days === 1 ? "" : "s"} ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
}

/** Warn when a project has not been opened recently (14+ days). */
export function isStaleProject(lastOpenedAt: string | null | undefined): boolean {
  if (!lastOpenedAt) return false;
  const then = new Date(lastOpenedAt);
  if (Number.isNaN(then.getTime())) return false;
  const days = (Date.now() - then.getTime()) / (1000 * 60 * 60 * 24);
  return days >= 14;
}

export function recommendedAction(input: {
  next_step: string | null | undefined;
  blocker: string | null | undefined;
  exit_note: string | null | undefined;
  has_unfinished_session?: boolean;
}): string {
  if (input.has_unfinished_session) {
    if (hasText(input.next_step)) {
      return input.next_step!.trim();
    }
    if (hasText(input.blocker)) {
      return `Resolve blocker: ${input.blocker!.trim()}`;
    }
    return "Active session in progress. Refresh context or end the session with an Exit Note when you finish.";
  }
  if (hasText(input.next_step)) {
    return input.next_step!.trim();
  }
  if (hasText(input.blocker)) {
    return `Resolve blocker: ${input.blocker!.trim()}`;
  }
  if (hasText(input.exit_note)) {
    return `Continue from: ${input.exit_note!.trim()}`;
  }
  return "Work on this project, then refresh context to capture where you stopped.";
}

export function sortProjectsByRecency<T extends { last_opened_at: string | null; updated_at: string }>(
  projects: T[]
): T[] {
  return [...projects].sort((a, b) => {
    const ta = a.last_opened_at ?? a.updated_at;
    const tb = b.last_opened_at ?? b.updated_at;
    return tb.localeCompare(ta);
  });
}

export function summaryPreviewText(project: {
  summary_preview: { headline: string; summary_text: string } | null;
  latest_session: {
    next_step: string | null;
    exit_note: string | null;
  } | null;
}): string {
  const preview = project.summary_preview;
  if (preview && hasText(preview.summary_text) && preview.headline !== preview.summary_text) {
    return preview.summary_text.trim();
  }
  if (preview && hasText(preview.headline) && preview.headline !== "Stored resume available") {
    return preview.headline.trim();
  }
  if (hasText(project.latest_session?.next_step)) {
    return `Next: ${project.latest_session!.next_step!.trim()}`;
  }
  if (hasText(project.latest_session?.exit_note)) {
    return `Last done: ${project.latest_session!.exit_note!.trim()}`;
  }
  if (preview?.headline === "Stored resume available") {
    return "Resume context available — see details below.";
  }
  return "No previous session summary yet.";
}

const SIDEBAR_SUMMARY_PREFIX_PATTERNS: RegExp[] = [
  /^where you left off:\s*/i,
  /^where you left off\s*[-—]\s*/i,
  /^suggested next step:\s*/i,
  /^next:\s*/i,
  /^last done:\s*/i,
  /^continue from:\s*/i,
  /^resolve blocker:\s*/i,
  /^project focus:\s*/i,
  /^blocked on:\s*/i,
  /^pinned note:\s*/i,
  /^uncommitted work on\b/i,
  /^uncommitted changes on branch\b/i,
  /^working tree clean on branch\b/i,
];

const SIDEBAR_SUMMARY_LINE_LABEL_PATTERNS: RegExp[] = [
  ...SIDEBAR_SUMMARY_PREFIX_PATTERNS,
  /^session still open\b/i,
  /^work in progress on\b/i,
  /^active session exists\b/i,
];

const SIDEBAR_SESSION_LINE_RE =
  /^(session still open|work in progress on|active session exists)\b/i;

const SIDEBAR_MAX_PREVIEW_CHARS = 280;

function trimSidebarPreview(text: string, limit: number): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (collapsed.length <= limit) {
    return collapsed;
  }
  let segment = collapsed.slice(0, limit - 1);
  const lastSpace = segment.lastIndexOf(" ");
  if (lastSpace > 0) {
    segment = segment.slice(0, lastSpace);
  }
  return `${segment.trimEnd()}…`;
}

/** Remove redundant label prefixes from one summary line (display only). */
export function stripSidebarSummaryLineLabel(text: string): string {
  let result = text.trim();
  let changed = true;

  while (changed) {
    changed = false;
    for (const pattern of SIDEBAR_SUMMARY_LINE_LABEL_PATTERNS) {
      const next = result.replace(pattern, "");
      if (next !== result) {
        result = next.trim();
        changed = true;
        break;
      }
    }
  }

  return result.replace(/\s+/g, " ").trim();
}

/** Remove redundant label prefixes for sidebar summary display only. */
function stripSidebarSummaryPrefix(text: string): string {
  return stripSidebarSummaryLineLabel(text);
}

function extractSidebarNextStepLine(summaryText: string): string | null {
  for (const rawLine of summaryText.split(/\n+/)) {
    const match = rawLine.match(/^suggested next step:\s*(.+)$/i);
    if (match && hasText(match[1])) {
      return stripSidebarSummaryLineLabel(match[1]);
    }
  }
  return null;
}

/** Compact sidebar preview from full dashboard summary text (display only). */
export function formatSidebarSummaryPreview(summaryText: string): string {
  const rawLines = summaryText
    .split(/\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const cleanedLines = rawLines
    .map(stripSidebarSummaryLineLabel)
    .filter((line) => hasText(line));

  const primaryLine =
    cleanedLines.find((line) => !SIDEBAR_SESSION_LINE_RE.test(line)) ??
    cleanedLines[0] ??
    "";

  const nextStep = extractSidebarNextStepLine(summaryText);

  let preview = primaryLine;
  if (nextStep && nextStep !== primaryLine) {
    preview = `${primaryLine} · Next: ${nextStep}`;
  }

  if (preview.length > SIDEBAR_MAX_PREVIEW_CHARS) {
    preview = trimSidebarPreview(preview, SIDEBAR_MAX_PREVIEW_CHARS);
  }

  return preview;
}

/** Sidebar-only summary preview with redundant prefixes removed. */
export function sidebarSummaryPreviewText(project: {
  summary_preview: { headline: string; summary_text: string } | null;
  latest_session: {
    next_step: string | null;
    exit_note: string | null;
  } | null;
}): string {
  const raw = summaryPreviewText(project);
  const formatted = formatSidebarSummaryPreview(raw);

  if (formatted) {
    return formatted;
  }

  const cleaned = stripSidebarSummaryPrefix(raw);

  if (cleaned) {
    return cleaned;
  }

  if (/^where you left off\.?$/i.test(raw.trim())) {
    return "No previous session summary yet.";
  }

  return raw;
}

/** Compact session label for sidebar project rows. */
export function sidebarSessionChip(
  session: { is_active: boolean } | null | undefined
): "Active" | "Closed" | "No session" {
  if (!session) return "No session";
  return session.is_active ? "Active" : "Closed";
}

/** Compact git label for sidebar project rows (no branch text). */
export function sidebarGitChip(state: string | undefined): "Dirty" | "Clean" | "No git" {
  if (state === "dirty") return "Dirty";
  if (state === "clean") return "Clean";
  return "No git";
}
