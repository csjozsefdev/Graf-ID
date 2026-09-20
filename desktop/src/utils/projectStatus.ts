/** Project lifecycle status (mirrors Python PROJECT_STATUSES). */

export const PROJECT_STATUSES = ["active", "paused", "archived"] as const;

export function statusLabel(status: string): string {
  switch (status) {
    case "paused":
      return "Paused";
    case "archived":
      return "Archived";
    default:
      return "Active";
  }
}
