/** Suggest a registry name from a folder path (last path segment). */
export function suggestProjectName(folderPath: string): string {
  const trimmed = folderPath.trim().replace(/[/\\]+$/, "");
  if (!trimmed) {
    return "project";
  }
  const parts = trimmed.split(/[/\\]/);
  const last = parts[parts.length - 1]?.trim();
  return last || "project";
}
