import { save } from "@tauri-apps/plugin-dialog";

import {
  exportProjectSummary,
  fetchExportSuggestedFilename,
  type ExportFormat,
} from "../ipc/client";

export class ExportCancelledError extends Error {
  constructor() {
    super("Export cancelled");
    this.name = "ExportCancelledError";
  }
}

const FILTERS: Record<ExportFormat, { name: string; extensions: string[] }> = {
  handoff: { name: "GrafiTalk handoff (JSON)", extensions: ["json"] },
  json: { name: "JSON", extensions: ["json"] },
  markdown: { name: "Markdown", extensions: ["md"] },
  txt: { name: "Plain text", extensions: ["txt"] },
};

/** Open save dialog and write export via backend Pretty Print / JSON formatter. */
export async function exportProjectToFile(
  projectId: number,
  format: ExportFormat
): Promise<string> {
  const suggested = await fetchExportSuggestedFilename(projectId, format);
  const path = await save({
    defaultPath: suggested.suggested_filename,
    filters: [FILTERS[format]],
  });
  if (!path) {
    throw new ExportCancelledError();
  }
  const result = await exportProjectSummary(projectId, format, path);
  return result.path;
}
