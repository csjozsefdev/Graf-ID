import { useState } from "react";
import { confirm, open, save } from "@tauri-apps/plugin-dialog";
import {
  createBackup,
  exportGrafiTalkInbox,
  getUserErrorMessage,
  openProjectFolderPath,
  restoreBackup,
} from "../../ipc/client";
import type { AppSettingsData } from "../../ipc/types";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../../utils/grafiHelpRegistry";
import { reloadApp } from "../../utils/reloadApp";

interface DataSectionProps {
  settings: AppSettingsData;
  saving: boolean;
  onNotice: (text: string | null) => void;
  onError: (text: string | null) => void;
}

/** Data folders, backup/restore and the GrafiTalk inbox export. */
export function DataSection({ settings, saving, onNotice, onError }: DataSectionProps) {
  const [dataBusy, setDataBusy] = useState(false);
  const [dataMessage, setDataMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null
  );

  // Data actions report right next to their buttons: the sticky footer belongs to the
  // settings form above and would be off-screen from here.
  const runDataAction = async (action: () => Promise<string | null>) => {
    setDataBusy(true);
    setDataMessage(null);
    try {
      const message = await action();
      if (message) setDataMessage({ kind: "ok", text: message });
    } catch (err) {
      setDataMessage({ kind: "error", text: getUserErrorMessage(err) });
    } finally {
      setDataBusy(false);
    }
  };

  const handleCreateBackup = () =>
    runDataAction(async () => {
      const stamp = new Date().toISOString().slice(0, 10);
      const path = await save({
        title: "Save Graf-Id backup",
        defaultPath: `graf-id-backup-${stamp}.zip`,
        filters: [{ name: "Graf-Id backup", extensions: ["zip"] }],
      });
      if (!path) return null;
      const result = await createBackup(path);
      return `Backup saved to ${result.path}`;
    });

  const handleRestoreBackup = () =>
    runDataAction(async () => {
      const picked = await open({
        title: "Choose a Graf-Id backup",
        multiple: false,
        directory: false,
        filters: [{ name: "Graf-Id backup", extensions: ["zip"] }],
      });
      if (typeof picked !== "string") return null;
      const confirmed = await confirm(
        "Restoring replaces ALL current Graf-Id data (projects, sessions, notes and history) " +
          "with the contents of this backup.\n\nA safety copy of your current data is kept in " +
          "the \"backups\" folder inside your Graf-Id data folder.\n\nContinue?",
        { title: "Restore from backup", kind: "warning", okLabel: "Restore", cancelLabel: "Cancel" }
      );
      if (!confirmed) return null;
      const result = await restoreBackup(picked);
      window.setTimeout(reloadApp, 1500);
      return `${result.message} Reloading Graf-Id…`;
    });

  const handleExportInbox = () =>
    runDataAction(async () => {
      const folder = await open({
        title: "Choose a folder for the GrafiTalk handoff files",
        multiple: false,
        directory: true,
      });
      if (typeof folder !== "string") return null;
      const result = await exportGrafiTalkInbox(folder);
      return `${result.message} Folder: ${result.folder}`;
    });

  const openFolder = async (path: string, label: string) => {
    onError(null);
    onNotice(null);
    try {
      await openProjectFolderPath(path);
      onNotice(`Opened ${label} in File Explorer.`);
    } catch (err) {
      onError(`${label}: ${getUserErrorMessage(err)}`);
    }
  };

  return (
    <>
    {settings ? (
      <div className="settings-page__block">
        <h3>Data folders</h3>
        <p className="muted settings-page__path">{settings.data_dir}</p>
        <div className="settings-form__actions">
          <button
            type="button"
            disabled={saving}
            onClick={() => void openFolder(settings.data_dir, "data folder")}
            {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_OPEN_DATA_FOLDER)}
          >
            Open data folder
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void openFolder(settings.logs_dir, "logs folder")}
            {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_OPEN_LOGS_FOLDER)}
          >
            Open logs folder
          </button>
        </div>
      </div>
    ) : null}

    {settings ? (
      <div className="settings-page__block">
        <h3>Backup and export</h3>
        <div className="settings-form__actions">
          <button type="button" disabled={saving || dataBusy} onClick={() => void handleCreateBackup()}>
            Create backup…
          </button>
          <button type="button" disabled={saving || dataBusy} onClick={() => void handleRestoreBackup()}>
            Restore from backup…
          </button>
          <button type="button" disabled={saving || dataBusy} onClick={() => void handleExportInbox()}>
            Export all projects…
          </button>
        </div>
        {dataMessage ? (
          <p
            className={
              dataMessage.kind === "error"
                ? "error-text"
                : "settings-field__notice settings-field__notice--ok"
            }
            role={dataMessage.kind === "error" ? "alert" : "status"}
          >
            {dataMessage.text}
          </p>
        ) : null}
        <p className="muted settings-field__hint">
          <strong>Backup</strong> saves one .zip with your projects, sessions, notes and history
          (settings, editor paths and coding agents are not included).{" "}
          <strong>Restore</strong> replaces the current data and keeps a safety copy.{" "}
          <strong>Export all projects</strong> writes one GrafiTalk-compatible handoff file per
          project into a folder you choose — no local folder paths are included.
        </p>
      </div>
    ) : null}
    </>
  );
}
