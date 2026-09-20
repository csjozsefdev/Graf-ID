interface RemoveProjectDialogProps {
  open: boolean;
  projectName: string;
  removing: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RemoveProjectDialog({
  open,
  projectName,
  removing,
  error,
  onConfirm,
  onCancel,
}: RemoveProjectDialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="remove-project-overlay" role="dialog" aria-labelledby="remove-project-title">
      <div className="remove-project-dialog">
        <h2 id="remove-project-title">Remove from Graf-Id?</h2>
        <p>
          Remove <strong>{projectName}</strong> from your Graf-Id project list?
        </p>
        <p className="muted">
          This only removes the project from Graf-Id. It does not delete files from your computer.
        </p>
        {error ? <p className="error-text">{error}</p> : null}
        <div className="remove-project-dialog__actions">
          <button type="button" disabled={removing} onClick={onConfirm}>
            {removing ? "Removing…" : "Remove from Graf-Id"}
          </button>
          <button type="button" disabled={removing} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
