import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../../utils/grafiHelpRegistry";
import type { SetDraft, SettingsDraft } from "./settingsDraft";

interface GrafiSectionProps {
  draft: SettingsDraft;
  setDraft: SetDraft;
  saving: boolean;
}

/** Grafi advisor toggles (stored in the browser, not in config.json). */
export function GrafiSection({ draft, setDraft, saving }: GrafiSectionProps) {
  return (
    <>
    <h3 className="settings-form__section-title">Grafi advisor</h3>

    <div className="settings-field settings-field--checkbox">
      <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_GRAFI_ENABLED)}>
        <input
          type="checkbox"
          checked={draft.grafi_enabled}
          disabled={saving}
          onChange={(e) =>
            setDraft((prev) =>
              prev ? { ...prev, grafi_enabled: e.target.checked } : prev
            )
          }
        />
        Show Grafi advisor
      </label>
    </div>

    <div className="settings-field settings-field--checkbox">
      <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_HELPING_MODE)}>
        <input
          type="checkbox"
          checked={draft.grafi_helping_mode_enabled}
          disabled={saving || !draft.grafi_enabled}
          onChange={(e) =>
            setDraft((prev) =>
              prev ? { ...prev, grafi_helping_mode_enabled: e.target.checked } : prev
            )
          }
        />
        Helping Mode (UI tips on hover and focus)
      </label>
    </div>

    <div className="settings-field settings-field--checkbox">
      <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_GRAFI_MOTION)}>
        <input
          type="checkbox"
          checked={draft.grafi_motion_enabled}
          disabled={saving || !draft.grafi_enabled}
          onChange={(e) =>
            setDraft((prev) =>
              prev ? { ...prev, grafi_motion_enabled: e.target.checked } : prev
            )
          }
        />
        Enable motion
      </label>
    </div>

    <div className="settings-field settings-field--checkbox">
      <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_GRAFI_CRITICAL_ONLY)}>
        <input
          type="checkbox"
          checked={draft.grafi_critical_alerts_only}
          disabled={saving || !draft.grafi_enabled}
          onChange={(e) =>
            setDraft((prev) =>
              prev
                ? { ...prev, grafi_critical_alerts_only: e.target.checked }
                : prev
            )
          }
        />
        Critical alerts only
      </label>
    </div>
    </>
  );
}
