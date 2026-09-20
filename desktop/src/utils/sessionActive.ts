import type { DashboardProject } from "../ipc/types";

/** True when the project has an unfinished work session in Graf-Id. */
export function projectHasOpenSession(
  project: Pick<DashboardProject, "has_open_session" | "latest_session">
): boolean {
  if (project.has_open_session) {
    return true;
  }
  return project.latest_session?.is_active === true;
}
