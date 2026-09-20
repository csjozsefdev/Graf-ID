import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectDetailHeader } from "./ProjectDetailHeader";
import type { DashboardProject } from "../ipc/types";

const project = {
  id: 1,
  name: "Alpha",
  path: "C:\\alpha",
  path_accessible: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_opened_at: null,
  preferred_ide: null,
  is_active: false,
  category: "Personal Projects",
  status: "active",
  notes: null,
  last_refreshed_at: null,
  latest_session: null,
  summary_preview: null,
  git_status: { state: "unknown", label: "No scan yet", is_git_repo: false, is_dirty: false, branch: null },
  has_resume: false,
  open_task_count: null,
  latest_scan_at: null,
} as DashboardProject;

describe("ProjectDetailHeader — export and import actions", () => {
  it("offers GrafiTalk handoff, JSON, Markdown and TXT as separate, named exports", () => {
    const onExport = vi.fn();
    render(<ProjectDetailHeader project={project} onExport={onExport} />);
    const group = screen.getByRole("group", { name: "Export summary" });
    const labels = Array.from(group.querySelectorAll("button")).map((b) => b.textContent);
    expect(labels).toEqual(["GrafiTalk handoff", "JSON", "Markdown", "TXT"]);

    fireEvent.click(screen.getByRole("button", { name: "GrafiTalk handoff" }));
    fireEvent.click(screen.getByRole("button", { name: "JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Markdown" }));
    fireEvent.click(screen.getByRole("button", { name: "TXT" }));
    expect(onExport.mock.calls.map((c) => c[0])).toEqual(["handoff", "json", "markdown", "txt"]);
  });

  it("has an Import context action that is disabled while busy", () => {
    const onImport = vi.fn();
    const { rerender } = render(<ProjectDetailHeader project={project} onImportContext={onImport} />);
    fireEvent.click(screen.getByRole("button", { name: "Import context…" }));
    expect(onImport).toHaveBeenCalledTimes(1);
    rerender(<ProjectDetailHeader project={project} onImportContext={onImport} exportBusy />);
    expect(screen.getByRole("button", { name: "Import context…" })).toBeDisabled();
  });
});
