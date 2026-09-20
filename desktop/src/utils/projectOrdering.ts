import type { DashboardProject } from "../ipc/types";
import { sortProjectsByRecency } from "./continuity";

export function hasExplicitSidebarOrder(
  projects: Pick<DashboardProject, "sidebar_order">[]
): boolean {
  return projects.some((project) => project.sidebar_order != null);
}

export function sortProjectsForSidebar<T extends DashboardProject>(projects: T[]): T[] {
  if (!hasExplicitSidebarOrder(projects)) {
    return sortProjectsByRecency(projects);
  }
  return [...projects].sort((left, right) => {
    const leftOrder = left.sidebar_order;
    const rightOrder = right.sidebar_order;
    if (leftOrder == null && rightOrder == null) {
      return sortProjectsByRecency([left, right])[0] === left ? -1 : 1;
    }
    if (leftOrder == null) {
      return 1;
    }
    if (rightOrder == null) {
      return -1;
    }
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
  });
}

export function applyReorder(
  globalIds: number[],
  draggedId: number,
  targetIndex: number
): number[] {
  const fromIndex = globalIds.indexOf(draggedId);
  if (fromIndex < 0) {
    return globalIds;
  }
  const clampedTarget = Math.max(0, Math.min(targetIndex, globalIds.length - 1));
  const next = [...globalIds];
  next.splice(fromIndex, 1);
  next.splice(clampedTarget, 0, draggedId);
  return next;
}

export function applyFilteredReorder(
  globalIds: number[],
  visibleIds: number[],
  draggedId: number,
  targetVisibleIndex: number
): number[] {
  if (!visibleIds.includes(draggedId)) {
    return globalIds;
  }
  const clampedTarget = Math.max(0, Math.min(targetVisibleIndex, visibleIds.length - 1));
  const withoutDragged = globalIds.filter((id) => id !== draggedId);
  if (clampedTarget === 0) {
    const anchor = visibleIds.find((id) => id !== draggedId);
    if (anchor == null) {
      return globalIds;
    }
    const anchorIndex = withoutDragged.indexOf(anchor);
    if (anchorIndex < 0) {
      return globalIds;
    }
    const next = [...withoutDragged];
    next.splice(anchorIndex, 0, draggedId);
    return next;
  }
  const anchor = visibleIds[clampedTarget - 1];
  if (anchor === draggedId) {
    return globalIds;
  }
  const anchorIndex = withoutDragged.indexOf(anchor);
  if (anchorIndex < 0) {
    return globalIds;
  }
  const next = [...withoutDragged];
  next.splice(anchorIndex + 1, 0, draggedId);
  return next;
}

export function initializeSidebarOrderIds(projects: DashboardProject[]): number[] {
  return sortProjectsForSidebar(projects).map((project) => project.id);
}
