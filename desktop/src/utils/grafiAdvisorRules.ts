import type { DashboardProject, NavSection, ResumePanelData } from "../ipc/types";
import type { GrafiAction, GrafiSeverity } from "../shared/grafi-advisor";
import { hasText, isStaleProject } from "./continuity";
import { partitionMvpSections } from "./resumeSections";

export const RECENT_EXIT_NOTE_DAYS = 7;
export const SEVERAL_FILES_THRESHOLD = 3;
const STALE_SCAN_HOURS = 24;

export const GRAFI_HOST_READY_MESSAGE =
  "Project context is ready. Review the latest summary when you are ready.";

export interface GrafiAdvisorCandidate {
  message: string;
  severity: GrafiSeverity;
  priority: number;
}

export interface GrafiAdvisorBrief {
  messages: string[];
  severity: GrafiSeverity;
  actions: GrafiAction[];
}

export const OPEN_SUMMARY_ACTION: GrafiAction = {
  id: "open-summary",
  label: "Open summary",
  variant: "primary",
};

function normalizeMessage(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function dedupeMessages(messages: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const message of messages) {
    const key = normalizeMessage(message);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(message.trim());
  }
  return result;
}

function severityRank(severity: GrafiSeverity): number {
  switch (severity) {
    case "critical":
      return 4;
    case "warning":
      return 3;
    case "success":
      return 2;
    default:
      return 1;
  }
}

function pickSeverity(candidates: GrafiAdvisorCandidate[]): GrafiSeverity {
  return candidates.reduce<GrafiSeverity>(
    (current, candidate) =>
      severityRank(candidate.severity) > severityRank(current)
        ? candidate.severity
        : current,
    "info"
  );
}

function hoursSince(iso: string | null | undefined): number | null {
  if (!iso) {
    return null;
  }
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) {
    return null;
  }
  return (Date.now() - then.getTime()) / (1000 * 60 * 60);
}

function daysSince(iso: string | null | undefined): number | null {
  const hours = hoursSince(iso);
  return hours == null ? null : hours / 24;
}

export function hasActiveBlocker(
  panel: ResumePanelData,
  sections: ReturnType<typeof partitionMvpSections>
): boolean {
  if (hasText(panel.blocker)) {
    return true;
  }
  if (
    sections.primary.some((section) => section.title.trim().toLowerCase() === "blocker") &&
    hasText(sections.primary.find((section) => section.title.trim().toLowerCase() === "blocker")?.body)
  ) {
    return true;
  }
  return Boolean(
    panel.latest_session?.is_active &&
      hasText(panel.blocker) &&
      !hasText(panel.next_step)
  );
}

export function hasRefreshProblem(panel: ResumePanelData): boolean {
  const neverScanned = !panel.has_stored_resume && !panel.latest_scan_at;
  if (neverScanned || panel.last_refreshed_at == null) {
    return true;
  }
  const sessionEndedAt = panel.latest_session?.ended_at ?? null;
  const scanReference = panel.latest_scan_at ?? panel.last_refreshed_at ?? null;
  if (sessionEndedAt && scanReference) {
    const sessionEnded = new Date(sessionEndedAt);
    const scanAt = new Date(scanReference);
    if (
      !Number.isNaN(sessionEnded.getTime()) &&
      !Number.isNaN(scanAt.getTime()) &&
      scanAt.getTime() < sessionEnded.getTime()
    ) {
      return true;
    }
  }
  const scanAgeHours = hoursSince(scanReference);
  return scanAgeHours != null && scanAgeHours > STALE_SCAN_HOURS && !panel.latest_session?.is_active;
}

export function hasRecentExitNote(panel: ResumePanelData): boolean {
  if (!hasText(panel.exit_note)) {
    return false;
  }
  if (panel.latest_session?.is_active) {
    return true;
  }
  const endedAt = panel.latest_session?.ended_at;
  const ageDays = daysSince(endedAt);
  return ageDays != null && ageDays <= RECENT_EXIT_NOTE_DAYS;
}

export function hasMissingContinuityData(panel: ResumePanelData): boolean {
  if (!panel.has_stored_resume && !panel.latest_scan_at) {
    return false;
  }
  return (
    !hasText(panel.exit_note) &&
    !hasText(panel.next_step) &&
    !hasText(panel.blocker) &&
    !hasText(panel.stored_resume_excerpt) &&
    !panel.has_stored_resume
  );
}

export function buildGrafiAdvisorCandidates(
  project: DashboardProject,
  panel: ResumePanelData
): GrafiAdvisorCandidate[] {
  const sections = partitionMvpSections(panel.mvp_sections ?? []);
  const candidates: GrafiAdvisorCandidate[] = [];

  if (project.path_accessible === false) {
    candidates.push({
      priority: 1,
      severity: "critical",
      message: "Project folder not found at the registered path.",
    });
  }

  if (hasActiveBlocker(panel, sections)) {
    const blockerText = panel.blocker?.trim();
    candidates.push({
      priority: 2,
      severity: "warning",
      message: blockerText
        ? `Active blocker: ${blockerText}`
        : "Active blocker recorded for this project.",
    });
  }

  if (hasRefreshProblem(panel)) {
    candidates.push({
      priority: 3,
      severity: "warning",
      message: "Refresh context to update scan data and resume details.",
    });
  }

  if (panel.git_status.is_git_repo && panel.git_status.is_dirty) {
    const branch = panel.git_status.branch ? ` on ${panel.git_status.branch}` : "";
    candidates.push({
      priority: 4,
      severity: "warning",
      message: `Git working tree is dirty${branch}.`,
    });
  }

  if (hasMissingContinuityData(panel)) {
    candidates.push({
      priority: 5,
      severity: "info",
      message: "Continuity details are still thin. Refresh context or add an Exit Note.",
    });
  }

  if (hasRecentExitNote(panel)) {
    candidates.push({
      priority: 6,
      severity: "info",
      message: "Recent Exit Note available. Continue from the summary below.",
    });
  }

  if (panel.modified_files.length >= SEVERAL_FILES_THRESHOLD) {
    candidates.push({
      priority: 6,
      severity: "info",
      message: `${panel.modified_files.length} modified files tracked in the latest context.`,
    });
  }

  if (isStaleProject(panel.last_opened_at ?? project.last_opened_at)) {
    candidates.push({
      priority: 6,
      severity: "info",
      message: "This project has not been opened recently.",
    });
  }

  if (panel.latest_session?.is_active && !hasText(panel.exit_note)) {
    candidates.push({
      priority: 6,
      severity: "info",
      message: "Session still open. End it with an Exit Note when you stop.",
    });
  }

  return candidates.sort((left, right) => left.priority - right.priority);
}

export function resolveGrafiAdvisorBrief(input: {
  nav: NavSection;
  project: DashboardProject | null;
  panel: ResumePanelData | null;
  projectSelected: boolean;
  detailReady: boolean;
  detailError?: string | null;
}): GrafiAdvisorBrief | null {
  if (input.nav !== "dashboard" || !input.projectSelected || !input.project) {
    return null;
  }

  if (hasText(input.detailError)) {
    return {
      messages: [
        `Could not load project context. ${input.detailError!.trim()} Use Retry on the resume panel.`,
      ],
      severity: "warning",
      actions: [OPEN_SUMMARY_ACTION],
    };
  }

  if (!input.detailReady || !input.panel) {
    return null;
  }

  const candidates = buildGrafiAdvisorCandidates(input.project, input.panel);
  if (candidates.length === 0) {
    return {
      messages: [GRAFI_HOST_READY_MESSAGE],
      severity: "info",
      actions: [OPEN_SUMMARY_ACTION],
    };
  }

  const warnings = candidates.filter(
    (candidate) => candidate.severity === "warning" || candidate.severity === "critical"
  );
  const infos = candidates.filter((candidate) => candidate.severity === "info");
  const selected = [...warnings.slice(0, 2), ...infos.slice(0, Math.max(0, 2 - warnings.length))];
  const messages = dedupeMessages(selected.map((candidate) => candidate.message)).slice(0, 2);
  if (messages.length === 0) {
    return null;
  }

  return {
    messages,
    severity: pickSeverity(selected),
    actions: [OPEN_SUMMARY_ACTION],
  };
}

export function formatGrafiHostMessage(brief: GrafiAdvisorBrief | null): string | null {
  if (!brief || brief.messages.length === 0) {
    return null;
  }
  return brief.messages.join(" ");
}
