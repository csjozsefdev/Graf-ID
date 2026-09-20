import { describe, expect, it } from "vitest";

import { mergeDashboardProject } from "./projectMerge";
import type { DashboardProject } from "../ipc/types";

describe("PRO dashboard merge", () => {
  it("preserves has_open_session from refresh patch", () => {
    const base: DashboardProject = {
      id: 1,
      name: "demo",
      path: "/tmp/demo",
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
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
        label: "Unknown",
        is_git_repo: false,
        is_dirty: false,
        branch: null,
      },
      has_resume: false,
      open_task_count: null,
      latest_scan_at: null,
    };
    const merged = mergeDashboardProject(base, { ...base, has_open_session: true });
    expect(merged.has_open_session).toBe(true);
  });
});
