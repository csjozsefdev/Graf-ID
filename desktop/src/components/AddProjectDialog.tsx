import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { addProject, getUserErrorMessage } from "../ipc/client";
import type { DashboardProject } from "../ipc/types";
import {
  DEFAULT_PROJECT_CATEGORY,
  PROJECT_CATEGORIES,
  type ProjectCategory,
} from "../utils/projectCategories";
import { suggestProjectName } from "../utils/projectName";

interface AddProjectDialogProps {
  open: boolean;
  onClose: () => void;
  onAdded: (project: DashboardProject, message: string) => void;
}

export function AddProjectDialog({ open: isOpen, onClose, onAdded }: AddProjectDialogProps) {
  const [folderPath, setFolderPath] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [category, setCategory] = useState<ProjectCategory>(DEFAULT_PROJECT_CATEGORY);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setFolderPath(null);
      setName("");
      setCategory(DEFAULT_PROJECT_CATEGORY);
      setError(null);
      setSaving(false);
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const pickFolder = async () => {
    setError(null);
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Select project folder",
      });
      if (typeof selected === "string" && selected.trim()) {
        setFolderPath(selected);
        setName(suggestProjectName(selected));
      }
    } catch (err) {
      setError(getUserErrorMessage(err));
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!folderPath) {
      setError("Choose a project folder first.");
      return;
    }
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("Project name cannot be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await addProject(trimmedName, folderPath, category);
      onAdded(result.project, result.message);
      onClose();
    } catch (err) {
      setError(getUserErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="add-project-overlay" role="dialog" aria-labelledby="add-project-title">
      <form className="add-project-dialog" onSubmit={(e) => void handleSubmit(e)}>
        <header className="add-project-dialog__header">
          <h2 id="add-project-title">Add New Project (Scan)</h2>
          <p className="muted">
            Register a folder so Graf-Id can track sessions, scans, and resume context for it.
          </p>
        </header>

        <div className="add-project-dialog__field">
          <span className="label">Project folder</span>
          {folderPath ? (
            <p className="add-project-dialog__path">{folderPath}</p>
          ) : (
            <p className="muted">No folder selected yet.</p>
          )}
          <button type="button" disabled={saving} onClick={() => void pickFolder()}>
            Choose folder…
          </button>
        </div>

        <div className="add-project-dialog__field">
          <label htmlFor="add-project-name">Project name</label>
          <input
            id="add-project-name"
            type="text"
            value={name}
            disabled={saving}
            onChange={(e) => setName(e.target.value)}
            placeholder="Suggested from folder name"
          />
        </div>

        <div className="add-project-dialog__field">
          <label htmlFor="add-project-category">Category</label>
          <select
            id="add-project-category"
            value={category}
            disabled={saving}
            onChange={(e) => setCategory(e.target.value as ProjectCategory)}
          >
            {PROJECT_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        {error ? <p className="error-text">{error}</p> : null}

        <div className="add-project-dialog__actions">
          <button type="submit" disabled={saving || !folderPath}>
            {saving ? "Adding…" : "Add New Project (Scan)"}
          </button>
          <button type="button" disabled={saving} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
