import { describe, expect, it } from "vitest";
import type { DashboardProject } from "../ipc/types";
import { mergeDashboardProject } from "./projectMerge";

const base: DashboardProject = {
  id: 1,
  name: "demo",
  path: "/tmp/demo",
  created_at: "t",
  updated_at: "t",
  last_opened_at: null,
  preferred_ide: null,
  is_active: false,
  category: "Personal Projects",
  status: "active",
  notes: null,
  last_refreshed_at: null,
  latest_session: null,
  summary_preview: null,
  git_status: {
    state: "unknown",
    label: "No scan yet",
    is_git_repo: false,
    is_dirty: false,
    branch: null,
  },
  has_resume: false,
  open_task_count: null,
  latest_scan_at: null,
};

describe("mergeDashboardProject", () => {
  it("merges status and notes from patch", () => {
    const merged = mergeDashboardProject(base, {
      ...base,
      status: "paused",
      notes: "On hold",
    });
    expect(merged.status).toBe("paused");
    expect(merged.notes).toBe("On hold");
  });
});
