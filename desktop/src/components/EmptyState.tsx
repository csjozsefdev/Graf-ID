interface EmptyStateProps {
  title: string;
  message: string;
  hint?: string;
  dataFolder?: string;
  onAddProject?: () => void;
}

export function EmptyState({
  title,
  message,
  hint,
  dataFolder,
  onAddProject,
}: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <h3>{title}</h3>
      <p>{message}</p>
      {dataFolder ? (
        <p className="empty-state__hint muted">
          Current data folder: <code className="empty-state__path">{dataFolder}</code>
        </p>
      ) : null}
      {hint ? <p className="empty-state__hint muted">{hint}</p> : null}
      <div className="empty-state__actions">
        {onAddProject ? (
          <button type="button" className="empty-state__action" onClick={onAddProject}>
            Add project
          </button>
        ) : null}
      </div>
    </div>
  );
}
