/**
 * Map IPC / backend error codes to user-facing English messages.
 */

const FRIENDLY_MESSAGES: Record<string, string> = {
  backend_unavailable:
    "The local Python backend could not start. For development, use the project .venv or set GRAFID_PYTHON.",
  backend_command_failed:
    "A backend command failed. See desktop-backend.log in your Graf-Id data folder for details.",
  config_error:
    "Configuration could not be read. Check config.json in your Graf-Id data folder or delete it to reset defaults.",
  database_error:
    "The local database failed integrity checks. Run graf-id db check from a terminal or restore a backup.",
  startup_error: "Application startup failed. See logs in your Graf-Id data folder.",
  permission_error: "Graf-Id cannot write to the config or data directory. Check folder permissions.",
  project_error: "That project was not found in the local registry.",
  duplicate_project: "That project name or folder path is already registered.",
  validation_error: "The project folder path or name is not valid.",
  launch_failed: "Could not open the project for continued work.",
  runtime_validation_failed: "Packaged runtime validation failed. Paths or bundled files may be missing.",
  runtime_error: "An unexpected backend error occurred.",
  ipc_error: "The desktop shell could not reach the backend.",
  timeout: "The backend did not respond in time. It may be busy — try again.",
  unknown: "Something went wrong. Try again or restart the app.",
};

export function parseErrorCode(message: string): { code: string; detail: string } {
  const match = /^([\w_]+):\s*(.*)$/s.exec(message.trim());
  if (match) {
    return { code: match[1], detail: match[2].trim() };
  }
  if (message.includes("backend_unavailable")) {
    return { code: "backend_unavailable", detail: message };
  }
  return { code: "unknown", detail: message };
}

export function formatUserError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  const { code, detail } = parseErrorCode(raw);
  const friendly = FRIENDLY_MESSAGES[code];
  if (friendly) {
    return detail && detail !== friendly ? `${friendly} (${detail})` : friendly;
  }
  return detail || raw;
}
