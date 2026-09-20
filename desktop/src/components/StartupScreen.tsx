interface StartupScreenProps {
  errorTitle: string | null;
  errorMessage: string;
  onRetry: () => void;
}

/** Bootstrap failure screen (shown after splash fades out). */
export function StartupScreen({
  errorTitle,
  errorMessage,
  onRetry,
}: StartupScreenProps) {
  return (
    <div className="startup startup--error" role="alert">
      <h2>{errorTitle ?? "Startup failed"}</h2>
      <p>{errorMessage}</p>
      <button type="button" className="startup__button" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
