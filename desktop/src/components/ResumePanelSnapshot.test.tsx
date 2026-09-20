import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResumePanel } from "./ResumePanel";
import type { ProjectSnapshot, ResumePanelData } from "../ipc/types";

const gitStatus = { state: "clean" as const, label: "Clean", is_git_repo: true, is_dirty: false, branch: "main" };

function panel(snapshot: ProjectSnapshot | null): ResumePanelData {
  return {
    startup_summary: {
      headline: "Checkout finished",
      summary_text: "Where you left off: Checkout finished",
      scroll_excerpt: null,
      generated_at: "2026-09-20T00:00:00Z",
      source: "summary_engine",
      project_snapshot: snapshot,
      mvp_sections: [
        { title: "Where you left off", body: "Checkout finished" },
        { title: "Suggested next step", body: "Wire the receipt page" },
        { title: "Blocker", body: "Waiting for the API key" },
        { title: "Recent file changes", body: "src/a.ts" },
        { title: "Code markers (detail)", body: "Open markers in x.ts" },
      ],
    },
    blocker: null,
    next_step: null,
    exit_note: null,
    modified_files: [],
    stored_resume_excerpt: null,
    git_status: gitStatus,
    has_stored_resume: true,
    latest_session: null,
    last_opened_at: null,
    open_task_count: null,
    latest_scan_at: "2026-09-20T00:00:00Z",
  };
}

const SNAPSHOT: ProjectSnapshot = {
  current_focus: ["Checkout flow is finished."],
  open_issues: ["Waiting for the API key"],
  recent_fixes: ["Pin release runtime"],
  recent_improvements: [],
  suggested_next_step: "Wire the receipt page",
};

describe("ResumePanel — Where you left off, Project Snapshot, Evidence", () => {
  it("shows Where you left off first, then the Project Snapshot, then collapsed evidence", () => {
    render(<ResumePanel panel={panel(SNAPSHOT)} loading={false} error={null} />);
    const headings = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
    expect(headings.indexOf("Where you left off")).toBeLessThan(headings.indexOf("Project Snapshot"));

    const evidence = screen.getByText("Evidence & details").closest("details") as HTMLDetailsElement;
    expect(evidence.open).toBe(false);
    expect(within(evidence).getByText("Recent file changes")).toBeInTheDocument();
    expect(within(evidence).getByText("Code markers (detail)")).toBeInTheDocument();
  });

  it("does not repeat the next step and blocker the snapshot already shows", () => {
    render(<ResumePanel panel={panel(SNAPSHOT)} loading={false} error={null} />);
    expect(screen.getAllByText("Wire the receipt page")).toHaveLength(1);
    expect(screen.getAllByText("Waiting for the API key")).toHaveLength(1);
  });

  it("keeps the stand-alone next step / blocker sections when there is no snapshot", () => {
    render(<ResumePanel panel={panel(null)} loading={false} error={null} />);
    expect(screen.queryByLabelText("Project Snapshot")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Suggested next step" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Blocker" })).toBeInTheDocument();
  });

  it("keeps a generic next-step fallback the snapshot deliberately omits", () => {
    render(<ResumePanel panel={panel({ recent_fixes: ["Pin release runtime"] })} loading={false} error={null} />);
    expect(screen.getByRole("heading", { name: "Suggested next step" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project Snapshot")).toBeInTheDocument();
  });
});
