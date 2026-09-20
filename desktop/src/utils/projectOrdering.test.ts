import { describe, expect, it } from "vitest";
import type { DashboardProject } from "../ipc/types";
import {
  applyFilteredReorder,
  applyReorder,
  hasExplicitSidebarOrder,
  initializeSidebarOrderIds,
  sortProjectsForSidebar,
} from "./projectOrdering";

function project(
  id: number,
  overrides: Partial<DashboardProject> = {}
): DashboardProject {
  return {
    id,
    name: `Project ${id}`,
    path: `/tmp/${id}`,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-02T00:00:00",
    last_opened_at: `2026-01-0${id}T00:00:00`,
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
    ...overrides,
  };
}

describe("projectOrdering", () => {
  it("uses recency when no sidebar_order is stored", () => {
    const projects = [
      project(1, { last_opened_at: "2026-01-01T00:00:00" }),
      project(2, { last_opened_at: "2026-01-05T00:00:00" }),
    ];
    expect(hasExplicitSidebarOrder(projects)).toBe(false);
    expect(sortProjectsForSidebar(projects).map((item) => item.id)).toEqual([2, 1]);
  });

  it("sorts by sidebar_order when any project has stored order", () => {
    const projects = [
      project(1, { sidebar_order: 3 }),
      project(2, { sidebar_order: 1 }),
      project(3, { sidebar_order: 2 }),
    ];
    expect(sortProjectsForSidebar(projects).map((item) => item.id)).toEqual([2, 3, 1]);
  });

  it("reorders globally by dragged id and target index", () => {
    expect(applyReorder([1, 2, 3, 4], 4, 1)).toEqual([1, 4, 2, 3]);
  });

  it("splices filtered reorder into the global id list", () => {
    const globalIds = [1, 2, 3, 4, 5];
    const visibleIds = [2, 4, 5];
    expect(applyFilteredReorder(globalIds, visibleIds, 5, 0)).toEqual([1, 5, 2, 3, 4]);
    expect(applyFilteredReorder(globalIds, visibleIds, 2, 2)).toEqual([1, 3, 4, 2, 5]);
  });

  it("initializes order ids from the current sidebar sort", () => {
    const projects = [
      project(1, { sidebar_order: 2 }),
      project(2, { sidebar_order: 1 }),
    ];
    expect(initializeSidebarOrderIds(projects)).toEqual([2, 1]);
  });
});
