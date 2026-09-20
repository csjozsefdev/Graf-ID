import { describe, expect, it } from "vitest";
import {
  buildGrafiAdvisorCandidates,
  formatGrafiHostMessage,
  GRAFI_HOST_READY_MESSAGE,
  hasActiveBlocker,
  hasMissingContinuityData,
  hasRecentExitNote,
  hasRefreshProblem,
  RECENT_EXIT_NOTE_DAYS,
  resolveGrafiAdvisorBrief,
  SEVERAL_FILES_THRESHOLD,
} from "./grafiAdvisorRules";
import { healthyPanel, healthyProject, recentIso } from "./grafiAdvisorTestFixtures";

describe("grafiAdvisorRules", () => {
  it("returns ready fallback for a healthy recent project", () => {
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject(),
      panel: healthyPanel(),
      projectSelected: true,
      detailReady: true,
    });
    expect(brief?.messages).toEqual([GRAFI_HOST_READY_MESSAGE]);
    expect(brief?.severity).toBe("info");
  });

  it("detects active blocker from panel blocker text", () => {
    const resumePanel = healthyPanel({ blocker: "Waiting on API keys" });
    expect(hasActiveBlocker(resumePanel, { primary: [], secondary: [] })).toBe(true);
  });

  it("detects refresh problems when never scanned", () => {
    expect(
      hasRefreshProblem(
        healthyPanel({
          has_stored_resume: false,
          latest_scan_at: null,
          last_refreshed_at: null,
        })
      )
    ).toBe(true);
  });

  it("warns when detail context failed to load", () => {
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject(),
      panel: null,
      projectSelected: true,
      detailReady: false,
      detailError: "Backend unavailable",
    });
    expect(brief?.severity).toBe("warning");
    expect(brief?.messages[0]).toMatch(/Could not load project context/i);
    expect(brief?.messages[0]).toContain("Backend unavailable");
  });

  it("detects several modified files at threshold", () => {
    const resumePanel = healthyPanel({
      modified_files: ["a.ts", "b.ts", "c.ts"].slice(0, SEVERAL_FILES_THRESHOLD),
    });
    const candidates = buildGrafiAdvisorCandidates(healthyProject(), resumePanel);
    expect(
      candidates.some((candidate) => candidate.message.includes("modified files"))
    ).toBe(true);
  });

  it("detects recent exit note within configured days", () => {
    const recent = recentIso((RECENT_EXIT_NOTE_DAYS - 1) * 24);
    expect(
      hasRecentExitNote(
        healthyPanel({
          exit_note: "Finished auth flow",
          latest_session: {
            id: 1,
            started_at: recent,
            ended_at: recent,
            is_active: false,
            status: "completed",
            summary: null,
            exit_note: "Finished auth flow",
            blocker: null,
            next_step: null,
          },
        })
      )
    ).toBe(true);
  });

  it("detects missing continuity data", () => {
    expect(
      hasMissingContinuityData(
        healthyPanel({
          has_stored_resume: false,
          latest_scan_at: recentIso(1),
          exit_note: null,
          next_step: null,
          blocker: null,
          stored_resume_excerpt: null,
        })
      )
    ).toBe(true);
  });

  it("prioritizes missing path before dirty git warnings", () => {
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject({ path_accessible: false }),
      panel: healthyPanel({
        git_status: {
          state: "dirty",
          label: "Dirty",
          is_git_repo: true,
          is_dirty: true,
          branch: "main",
        },
      }),
      projectSelected: true,
      detailReady: true,
    });
    expect(brief?.severity).toBe("critical");
    expect(brief?.messages[0]).toMatch(/folder not found/i);
  });

  it("returns at most two deduplicated messages", () => {
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject(),
      panel: healthyPanel({
        blocker: "Waiting on API keys",
        git_status: {
          state: "dirty",
          label: "Dirty",
          is_git_repo: true,
          is_dirty: true,
          branch: "main",
        },
        modified_files: ["a.ts", "b.ts", "c.ts"],
        exit_note: "Continue docs",
        latest_session: {
          id: 1,
          started_at: recentIso(2),
          ended_at: recentIso(1),
          is_active: false,
          status: "completed",
          summary: null,
          exit_note: "Continue docs",
          blocker: "Waiting on API keys",
          next_step: null,
        },
      }),
      projectSelected: true,
      detailReady: true,
    });
    expect(brief?.messages.length).toBeLessThanOrEqual(2);
    expect(formatGrafiHostMessage(brief)).toContain("Active blocker");
  });

  it("flags stale projects with old last-opened timestamps", () => {
    const staleOpened = recentIso(15 * 24);
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject({ last_opened_at: staleOpened }),
      panel: healthyPanel({ last_opened_at: staleOpened }),
      projectSelected: true,
      detailReady: true,
    });
    expect(brief?.messages.some((m) => m.includes("not been opened recently"))).toBe(true);
  });

  it("returns null outside dashboard detail context", () => {
    expect(
      resolveGrafiAdvisorBrief({
        nav: "settings",
        project: healthyProject(),
        panel: healthyPanel(),
        projectSelected: true,
        detailReady: true,
      })
    ).toBeNull();
  });
});
