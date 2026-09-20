import { useEffect, useState } from "react";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";

export interface CloseSessionFormValues {
  exit_note: string;
  blocker: string;
  next_step: string;
  skip_notes: boolean;
}

interface CloseSessionDialogProps {
  open: boolean;
  projectName: string;
  closing: boolean;
  error: string | null;
  onSubmit: (values: CloseSessionFormValues) => void;
}

const EMPTY_FORM: CloseSessionFormValues = {
  exit_note: "",
  blocker: "",
  next_step: "",
  skip_notes: false,
};

export function CloseSessionDialog({
  open,
  projectName,
  closing,
  error,
  onSubmit,
}: CloseSessionDialogProps) {
  const [form, setForm] = useState<CloseSessionFormValues>(EMPTY_FORM);

  useEffect(() => {
    if (!open) {
      setForm(EMPTY_FORM);
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const handleSkip = () => {
    onSubmit({ ...EMPTY_FORM, skip_notes: true });
  };

  return (
    <div
      className="close-session-overlay"
      role="dialog"
      aria-labelledby="close-session-title"
      aria-modal="true"
    >
      <form
        className="close-session-dialog"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ ...form, skip_notes: false });
        }}
      >
        <h2 id="close-session-title">End session</h2>
        <p className="muted">
          Save where you left off on <strong>{projectName}</strong>. Closing your editor does
          not end the Graf-Id session — use this when you pause work.
        </p>

        <div className="close-session-dialog__field" {...grafiHelpProps(GRAFI_HELP_TOPIC.EXIT_NOTE)}>
          <label className="close-session-dialog__label" htmlFor="close-session-done">
            What did you do today?
          </label>
          <textarea
            id="close-session-done"
            className="close-session-dialog__textarea"
            rows={3}
            disabled={closing}
            placeholder="Optional — e.g. finished auth refactor, updated docs"
            value={form.exit_note}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, exit_note: event.target.value }))
            }
          />
        </div>

        <div className="close-session-dialog__field">
          <label className="close-session-dialog__label" htmlFor="close-session-blocker">
            Blocker
          </label>
          <input
            id="close-session-blocker"
            className="close-session-dialog__input"
            type="text"
            disabled={closing}
            placeholder="Optional"
            value={form.blocker}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, blocker: event.target.value }))
            }
          />
        </div>

        <div className="close-session-dialog__field">
          <label className="close-session-dialog__label" htmlFor="close-session-next">
            Next step
          </label>
          <input
            id="close-session-next"
            className="close-session-dialog__input"
            type="text"
            disabled={closing}
            placeholder="Optional"
            value={form.next_step}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, next_step: event.target.value }))
            }
          />
        </div>

        {error ? <p className="error-text">{error}</p> : null}

        <div className="close-session-dialog__actions">
          <button type="submit" disabled={closing}>
            {closing ? "Saving…" : "Save & end session"}
          </button>
          <button type="button" disabled={closing} onClick={handleSkip}>
            End without notes
          </button>
        </div>
      </form>
    </div>
  );
}
