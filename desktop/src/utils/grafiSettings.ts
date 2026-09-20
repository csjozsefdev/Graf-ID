import type { GrafiSettings } from "../shared/grafi-advisor";

const GRAFI_SETTINGS_STORAGE_KEY = "grafid.grafiSettings";

export const DEFAULT_GRAFI_SETTINGS: GrafiSettings = {
  enabled: true,
  motionEnabled: true,
  criticalAlertsOnly: false,
  helpingModeEnabled: true,
};

export function loadGrafiSettings(): GrafiSettings {
  if (typeof localStorage === "undefined") {
    return { ...DEFAULT_GRAFI_SETTINGS };
  }
  try {
    const raw = localStorage.getItem(GRAFI_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_GRAFI_SETTINGS };
    }
    const parsed = JSON.parse(raw) as Partial<GrafiSettings>;
    return {
      enabled: parsed.enabled ?? DEFAULT_GRAFI_SETTINGS.enabled,
      motionEnabled: parsed.motionEnabled ?? DEFAULT_GRAFI_SETTINGS.motionEnabled,
      criticalAlertsOnly:
        parsed.criticalAlertsOnly ?? DEFAULT_GRAFI_SETTINGS.criticalAlertsOnly,
      helpingModeEnabled:
        parsed.helpingModeEnabled ?? DEFAULT_GRAFI_SETTINGS.helpingModeEnabled,
    };
  } catch {
    return { ...DEFAULT_GRAFI_SETTINGS };
  }
}

export function saveGrafiSettings(settings: GrafiSettings): void {
  localStorage.setItem(GRAFI_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}

export function resetGrafiSettings(): GrafiSettings {
  const defaults = { ...DEFAULT_GRAFI_SETTINGS };
  saveGrafiSettings(defaults);
  return defaults;
}

export const GRAFI_SETTINGS_SAVED_EVENT = "grafid:grafi-settings-saved";

export function notifyGrafiSettingsSaved(): void {
  window.dispatchEvent(new CustomEvent(GRAFI_SETTINGS_SAVED_EVENT));
}
