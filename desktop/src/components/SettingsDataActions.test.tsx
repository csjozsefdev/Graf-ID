import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { DEFAULT_GRAFI_SETTINGS } from "../utils/grafiSettings";
import type { AppSettingsData } from "../ipc/types";

const settings: AppSettingsData = {
  data_dir: "C:\\data",
  logs_dir: "C:\\logs",
  config_dir: "C:\\config",
  config_path: "C:\\config\\config.json",
  default_project_opener: "system",
  usage_journal_enabled: false,
  debug_timing_enabled: false,
  compact_mode: false,
  opener_options: [{ id: "system", label: "Auto Detect (System default)" }],
  python_interpreter_mode: "auto",
  python_interpreter_custom_path: "",
  custom_opener_path: "",
  interpreter_options: [{ id: "auto", label: "Auto Detect" }],
  coding_agents: [],
};

const { createBackupMock, restoreBackupMock, exportInboxMock, saveMock, openMock, confirmMock, reloadMock } =
  vi.hoisted(() => ({
    createBackupMock: vi.fn(),
    restoreBackupMock: vi.fn(),
    exportInboxMock: vi.fn(),
    saveMock: vi.fn(),
    openMock: vi.fn(),
    confirmMock: vi.fn(),
    reloadMock: vi.fn(),
  }));

vi.mock("../utils/grafiSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/grafiSettings")>();
  return { ...actual, loadGrafiSettings: () => ({ ...DEFAULT_GRAFI_SETTINGS }) };
});

vi.mock("../ipc/client", () => ({
  fetchAppSettings: () => Promise.resolve(settings),
  saveAppSettings: vi.fn(),
  resetAppSettings: vi.fn(),
  openProjectFolderPath: vi.fn(),
  createBackup: (...a: unknown[]) => createBackupMock(...a),
  restoreBackup: (...a: unknown[]) => restoreBackupMock(...a),
  exportGrafiTalkInbox: (...a: unknown[]) => exportInboxMock(...a),
  getUserErrorMessage: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: (...a: unknown[]) => openMock(...a),
  save: (...a: unknown[]) => saveMock(...a),
  confirm: (...a: unknown[]) => confirmMock(...a),
}));

vi.mock("../utils/reloadApp", () => ({ reloadApp: () => reloadMock() }));

async function renderSettings() {
  render(<Settings />);
  await screen.findByRole("button", { name: "Create backup…" });
}

const flush = () => act(async () => {});

describe("Settings — backup, restore and GrafiTalk export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("creates a backup at the chosen path and reports it next to the buttons", async () => {
    saveMock.mockResolvedValue("C:\\Backups\\graf-id.zip");
    createBackupMock.mockResolvedValue({ path: "C:\\Backups\\graf-id.zip", bytes_written: 10, message: "Backup created." });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Create backup…" }));
    await flush();

    expect(createBackupMock).toHaveBeenCalledWith("C:\\Backups\\graf-id.zip");
    expect(screen.getByRole("status")).toHaveTextContent("Backup saved to C:\\Backups\\graf-id.zip");
    const dialog = saveMock.mock.calls[0][0] as { defaultPath: string; filters: { extensions: string[] }[] };
    expect(dialog.defaultPath).toMatch(/^graf-id-backup-\d{4}-\d{2}-\d{2}\.zip$/);
    expect(dialog.filters[0].extensions).toEqual(["zip"]);
  });

  it("does nothing when the backup save dialog is cancelled", async () => {
    saveMock.mockResolvedValue(null);
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Create backup…" }));
    await flush();
    expect(createBackupMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a backup failure as an alert without leaving the buttons disabled", async () => {
    saveMock.mockResolvedValue("C:\\x.zip");
    createBackupMock.mockRejectedValue(new Error("Could not write the backup: disk full"));
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Create backup…" }));
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("disk full");
    expect(screen.getByRole("button", { name: "Create backup…" })).not.toBeDisabled();
  });

  it("restore asks for explicit confirmation naming the safety copy, and does nothing if declined", async () => {
    openMock.mockResolvedValue("C:\\Backups\\graf-id.zip");
    confirmMock.mockResolvedValue(false);
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Restore from backup…" }));
    await flush();

    expect(confirmMock).toHaveBeenCalledTimes(1);
    const [text, options] = confirmMock.mock.calls[0] as [string, { kind: string }];
    expect(text).toMatch(/replaces ALL current Graf-Id data/);
    expect(text).toMatch(/safety copy/);
    expect(options.kind).toBe("warning");
    expect(restoreBackupMock).not.toHaveBeenCalled();
  });

  it("restore does nothing when no file is picked", async () => {
    openMock.mockResolvedValue(null);
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Restore from backup…" }));
    await flush();
    expect(confirmMock).not.toHaveBeenCalled();
    expect(restoreBackupMock).not.toHaveBeenCalled();
  });

  it("a confirmed restore runs, then reloads the app so nothing stale stays on screen", async () => {
    openMock.mockResolvedValue("C:\\Backups\\graf-id.zip");
    confirmMock.mockResolvedValue(true);
    restoreBackupMock.mockResolvedValue({
      project_count: 3, pre_restore_backup: "C:\\data\\backups\\x.db", settings_restored: [], message: "Restored 3 project(s).",
    });
    await renderSettings();
    vi.useFakeTimers({ toFake: ["setTimeout"] }); // only after the async render has settled

    fireEvent.click(screen.getByRole("button", { name: "Restore from backup…" }));
    await flush();

    expect(restoreBackupMock).toHaveBeenCalledWith("C:\\Backups\\graf-id.zip");
    expect(screen.getByRole("status")).toHaveTextContent("Restored 3 project(s). Reloading Graf-Id…");
    expect(reloadMock).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it("a failed restore reports the error and does not reload", async () => {
    openMock.mockResolvedValue("C:\\bad.zip");
    confirmMock.mockResolvedValue(true);
    restoreBackupMock.mockRejectedValue(new Error("Invalid backup: the file is not a valid zip archive."));
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Restore from backup…" }));
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("not a valid zip archive");
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it("Export all projects picks a folder and reports the result", async () => {
    openMock.mockResolvedValue("D:\\GrafiTalk\\inbox");
    exportInboxMock.mockResolvedValue({ folder: "D:\\GrafiTalk\\inbox", project_count: 4, message: "Exported 4 project handoff file(s)." });
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "Export all projects…" }));
    await flush();

    expect((openMock.mock.calls[0][0] as { directory: boolean }).directory).toBe(true);
    expect(exportInboxMock).toHaveBeenCalledWith("D:\\GrafiTalk\\inbox");
    expect(screen.getByRole("status")).toHaveTextContent("Exported 4 project handoff file(s). Folder: D:\\GrafiTalk\\inbox");
  });

  it("Export all projects is a no-op when the folder dialog is cancelled", async () => {
    openMock.mockResolvedValue(null);
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Export all projects…" }));
    await flush();
    expect(exportInboxMock).not.toHaveBeenCalled();
  });
});
