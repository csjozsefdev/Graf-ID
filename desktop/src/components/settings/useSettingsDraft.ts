import { useCallback, useEffect, useState } from "react";
import {
  fetchAppSettings,
  getUserErrorMessage,
  resetAppSettings,
  saveAppSettings,
} from "../../ipc/client";
import type { AppSettingsData } from "../../ipc/types";
import {
  notifyGrafiSettingsSaved,
  resetGrafiSettings,
  saveGrafiSettings,
} from "../../utils/grafiSettings";
import { applyCompactMode, grafiSettingsFromDraft, toDraft } from "./settingsDraft";
import type { SettingsDraft } from "./settingsDraft";

/** Loads the app settings and owns the editable draft plus save/reset. */
export function useSettingsDraft(onSettingsSaved?: (data: AppSettingsData) => void) {
  const [settings, setSettings] = useState<AppSettingsData | null>(null);
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    try {
      const data = await fetchAppSettings();
      setSettings(data);
      setDraft(toDraft(data));
      applyCompactMode(Boolean(data.compact_mode));
      setSettingsError(null);
    } catch (err) {
      setSettings(null);
      setDraft(null);
      setSettingsError(getUserErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setNotice(null);
    setSettingsError(null);
    try {
      const result = await saveAppSettings({
        default_project_opener: draft.default_project_opener,
        usage_journal_enabled: draft.usage_journal_enabled,
        debug_timing_enabled: draft.debug_timing_enabled,
        compact_mode: draft.compact_mode,
        python_interpreter_mode: draft.python_interpreter_mode,
        python_interpreter_custom_path: draft.python_interpreter_custom_path.trim() || null,
        custom_opener_path: draft.custom_opener_path.trim() || null,
        coding_agents: draft.codingAgents,
        removed_builtin_agents: draft.removedBuiltinAgents,
      });
      saveGrafiSettings(grafiSettingsFromDraft(draft));
      notifyGrafiSettingsSaved();
      setSettings(result);
      setDraft(toDraft(result));
      applyCompactMode(Boolean(result.compact_mode));
      setNotice(result.message);
      onSettingsSaved?.(result);
    } catch (err) {
      setSettingsError(getUserErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    setNotice(null);
    setSettingsError(null);
    try {
      const result = await resetAppSettings();
      resetGrafiSettings();
      notifyGrafiSettingsSaved();
      setSettings(result);
      setDraft(toDraft(result));
      applyCompactMode(Boolean(result.compact_mode));
      setNotice(result.message);
      onSettingsSaved?.(result);
    } catch (err) {
      setSettingsError(getUserErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return {
    settings,
    draft,
    setDraft,
    settingsError,
    setSettingsError,
    notice,
    setNotice,
    loading,
    saving,
    loadSettings,
    handleSave,
    handleReset,
  };
}

