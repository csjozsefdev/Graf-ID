import { useState } from "react";
import type { ContextImportMode, ContextImportPreview } from "../ipc/client";

interface ImportContextDialogProps {
  preview: ContextImportPreview | null;
  fileName: string;
  busy: boolean;
  error: string | null;
  onConfirm: (mode: ContextImportMode) => void;
  onCancel: () => void;
}

/** Review step for importing a handoff file: nothing is written until "Import" is clicked. */
export function ImportContextDialog({
  preview,
  fileName,
  busy,
  error,
  onConfirm,
  onCancel,
}: ImportContextDialogProps) {
  const [mode, setMode] = useState<ContextImportMode>("append");
  if (!preview) {
    return null;
  }
  const canImport = mode === "replace" || preview.fits;

  return (
    <div className="remove-project-overlay" role="dialog" aria-labelledby="import-context-title">
      <div className="remove-project-dialog import-context-dialog">
        <h2 id="import-context-title">Import context into {preview.project_name}?</h2>
        <p className="muted">
          File: <strong>{fileName}</strong> — review what will be saved. Nothing changes until you
          confirm.
        </p>

        {preview.warnings.map((warning) => (
          <p key={warning} className="error-text" role="alert">
            {warning}
          </p>
        ))}

        <h4>Will be saved to the project notes</h4>
        <pre className="import-context-dialog__preview">{preview.block}</pre>
        {preview.files_not_imported > 0 ? (
          <p className="muted">
            {preview.files_not_imported} listed file name(s) are not imported.
          </p>
        ) : null}

        <div role="radiogroup" aria-label="How to save" className="import-context-dialog__modes">
          <label>
            <input
              type="radio"
              name="import-mode"
              checked={mode === "append"}
              disabled={busy}
              onChange={() => setMode("append")}
            />{" "}
            Add below my existing notes (recommended)
          </label>
          <label>
            <input
              type="radio"
              name="import-mode"
              checked={mode === "replace"}
              disabled={busy}
              onChange={() => setMode("replace")}
            />{" "}
            Replace my existing notes
          </label>
        </div>
        {mode === "replace" && preview.current_notes ? (
          <p className="error-text" role="alert">
            This replaces your current notes ({preview.current_notes.length} characters).
          </p>
        ) : null}

        {error ? <p className="error-text" role="alert">{error}</p> : null}
        <div className="remove-project-dialog__actions">
          <button type="button" disabled={busy || !canImport} onClick={() => onConfirm(mode)}>
            {busy ? "Importing…" : "Import into project notes"}
          </button>
          <button type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
