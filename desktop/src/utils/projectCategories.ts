/** Lightweight project categories (mirrors Python PROJECT_CATEGORIES). */

export const PROJECT_CATEGORIES = [
  "Personal Projects",
  "Freelance Work",
  "Client Work",
  "Archived",
] as const;

export type ProjectCategory = (typeof PROJECT_CATEGORIES)[number];

export const DEFAULT_PROJECT_CATEGORY: ProjectCategory = "Personal Projects";

export function groupProjectsByCategory<T extends { category: string }>(
  projects: T[]
): Map<string, T[]> {
  const grouped = new Map<string, T[]>();
  for (const category of PROJECT_CATEGORIES) {
    grouped.set(category, []);
  }
  for (const project of projects) {
    const key = PROJECT_CATEGORIES.includes(project.category as ProjectCategory)
      ? project.category
      : DEFAULT_PROJECT_CATEGORY;
    grouped.get(key)!.push(project);
  }
  return grouped;
}
