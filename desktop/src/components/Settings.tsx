import { useEffect, useRef } from "react";
import type { AppSettingsData } from "../ipc/types";
import { isAgentOpenerValue, openerValueForAgent } from "../utils/codingAgents";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";
import { CodingAgentsSection } from "./settings/CodingAgentsSection";
import { DataSection } from "./settings/DataSection";
import { GrafiSection } from "./settings/GrafiSection";
import { pickExecutable } from "./settings/settingsDraft";
import { useSettingsDraft } from "./settings/useSettingsDraft";

interface SettingsProps {
  /** Lets a parent (AppShell) keep a fresh mirror of app_settings — e.g. for
   * agent-vs-editor Open Project routing — without re-fetching bootstrap. */
  onSettingsSaved?: (data: AppSettingsData) => void;
}

export function Settings({ onSettingsSaved }: SettingsProps = {}) {
  const {
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
  } = useSettingsDraft(onSettingsSaved);
  const lastEditorOpenerRef = useRef("system");
  const lastAgentOpenerRef = useRef<string | null>(null);

  const openerOptions = settings?.opener_options ?? [
    { id: "system", label: "Auto Detect (System default)" },
    { id: "cursor", label: "Cursor" },
    { id: "vscode", label: "VS Code" },
    { id: "explorer", label: "Explorer only" },
  ];

  const interpreterOptions = settings?.interpreter_options ?? [
    { id: "auto", label: "Auto Detect" },
    { id: "system", label: "System Python" },
    { id: "venv", label: ".venv (Virtual Environment)" },
    { id: "custom", label: "Custom Path" },
  ];

  const showCustomInterpreter = draft?.python_interpreter_mode === "custom";
  const showCustomOpener = draft?.default_project_opener === "custom";
  // A not-yet-saved custom agent (id === "") has no stable opener value yet
  // (M9: ids are system-generated on Save), so it isn't selectable until then.
  const agentOpenerOptions = (draft?.codingAgents ?? []).filter((a) => a.built_in || a.id !== "");
  const isAgentMode = isAgentOpenerValue(draft?.default_project_opener);
  const agentSettingsDirty =
    settings !== null &&
    draft !== null &&
    JSON.stringify([draft.codingAgents, draft.removedBuiltinAgents, draft.default_project_opener]) !==
      JSON.stringify([
        settings.coding_agents ?? [],
        settings.removed_builtin_agents ?? [],
        settings.default_project_opener,
      ]);

  // Remember the last choice on each side so flipping the toggle back and
  // forth restores it instead of resetting to a default.
  useEffect(() => {
    const value = draft?.default_project_opener;
    if (!value) return;
    if (isAgentOpenerValue(value)) {
      lastAgentOpenerRef.current = value;
    } else {
      lastEditorOpenerRef.current = value;
    }
  }, [draft?.default_project_opener]);

  const switchOpenerMode = (mode: "editor" | "agent") => {
    setDraft((prev) => {
      if (!prev) return prev;
      if (mode === "editor") {
        return { ...prev, default_project_opener: lastEditorOpenerRef.current };
      }
      const options = prev.codingAgents.filter((a) => a.built_in || a.id !== "");
      const remembered = options.find(
        (a) => openerValueForAgent(a.id) === lastAgentOpenerRef.current
      );
      const pick = remembered ?? options.find((a) => a.available) ?? options[0];
      return pick ? { ...prev, default_project_opener: openerValueForAgent(pick.id) } : prev;
    });
  };

  return (
    <section className="settings-page">
      <h2>Settings</h2>
      <p className="muted">Local preferences stored in config.json in your Graf-Id data folder.</p>

      {loading ? <p className="muted">Loading settings…</p> : null}

      {settingsError && !draft ? (
        <div className="settings-page__block">
          <p className="error-text">{settingsError}</p>
          <button
            type="button"
            onClick={() => void loadSettings()}
            disabled={saving}
            {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_RETRY)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {draft && !loading ? (
        <form
          className="settings-page__block settings-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSave();
          }}
        >
          <div className="settings-field" {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_PYTHON_BACKEND)}>
            <label className="settings-field__label" htmlFor="python-interpreter-mode">
              Python backend
            </label>
            <select
              id="python-interpreter-mode"
              className="settings-field__select"
              value={draft.python_interpreter_mode}
              disabled={saving}
              onChange={(e) =>
                setDraft((prev) =>
                  prev ? { ...prev, python_interpreter_mode: e.target.value } : prev
                )
              }
            >
              {interpreterOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
            {settings?.python_interpreter_hint ? (
              <p className="muted settings-field__hint">{settings.python_interpreter_hint}</p>
            ) : (
              <p className="muted settings-field__hint">
                Release builds use the bundled runtime. Presets mainly affect development and custom
                overrides.
              </p>
            )}
          </div>

          {showCustomInterpreter ? (
            <div
              className="settings-field"
              {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_PYTHON_CUSTOM_PATH)}
            >
              <label className="settings-field__label" htmlFor="python-interpreter-custom-path">
                Custom Python path
              </label>
              <div className="settings-field__path-row">
                <input
                  id="python-interpreter-custom-path"
                  className="settings-field__input"
                  type="text"
                  value={draft.python_interpreter_custom_path}
                  disabled={saving}
                  placeholder="C:\\path\\to\\python.exe"
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev
                        ? { ...prev, python_interpreter_custom_path: e.target.value }
                        : prev
                    )
                  }
                />
                <button
                  type="button"
                  disabled={saving}
                  {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_PYTHON_CUSTOM_PATH)}
                  onClick={() => {
                    void pickExecutable("Choose Python executable").then((path) => {
                      if (path) {
                        setDraft((prev) =>
                          prev ? { ...prev, python_interpreter_custom_path: path } : prev
                        );
                      }
                    });
                  }}
                >
                  Browse…
                </button>
              </div>
            </div>
          ) : null}

          <div className="settings-field" {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_PROJECT_OPENER)}>
            <span className="settings-field__label" id="opener-mode-label">
              Open Project starts
            </span>
            <div
              className="segmented"
              role="radiogroup"
              aria-labelledby="opener-mode-label"
            >
              <button
                type="button"
                role="radio"
                aria-checked={!isAgentMode}
                className={"segmented__option" + (!isAgentMode ? " segmented__option--active" : "")}
                disabled={saving}
                onClick={() => switchOpenerMode("editor")}
              >
                Editor
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={isAgentMode}
                className={"segmented__option" + (isAgentMode ? " segmented__option--active" : "")}
                disabled={saving || (!isAgentMode && agentOpenerOptions.length === 0)}
                title={
                  agentOpenerOptions.length === 0
                    ? "Add a coding agent below first."
                    : undefined
                }
                onClick={() => switchOpenerMode("agent")}
              >
                Coding agent
              </button>
            </div>
            <p className="muted settings-field__hint">
              {isAgentMode
                ? "Coding agent: opens a terminal in the project folder and starts the agent there. No work session, no Exit Note — the agent keeps its own context."
                : "Editor: opens the project in your editor and tracks a work session, with an Exit Note when the editor closes."}
            </p>

            <label className="settings-field__label settings-field__label--spaced" htmlFor="default-project-opener">
              Open projects with
            </label>
            <select
              id="default-project-opener"
              className="settings-field__select"
              value={draft.default_project_opener}
              disabled={saving}
              onChange={(e) =>
                setDraft((prev) =>
                  prev ? { ...prev, default_project_opener: e.target.value } : prev
                )
              }
            >
              {isAgentMode
                ? agentOpenerOptions.map((agent) => (
                    <option key={agent.id} value={openerValueForAgent(agent.id)}>
                      {agent.display_name}
                      {agent.available ? "" : " (not found)"}
                    </option>
                  ))
                : openerOptions.map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.label}
                    </option>
                  ))}
            </select>
            <p className="muted settings-field__hint">
              Used when you click Open Project. Open Folder always uses File Explorer.
            </p>
          </div>

          {showCustomOpener ? (
            <div
              className="settings-field"
              {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_CUSTOM_OPENER_PATH)}
            >
              <label className="settings-field__label" htmlFor="custom-opener-path">
                Custom editor path
              </label>
              <div className="settings-field__path-row">
                <input
                  id="custom-opener-path"
                  className="settings-field__input"
                  type="text"
                  value={draft.custom_opener_path}
                  disabled={saving}
                  placeholder="C:\\path\\to\\editor.exe"
                  onChange={(e) =>
                    setDraft((prev) =>
                      prev ? { ...prev, custom_opener_path: e.target.value } : prev
                    )
                  }
                />
                <button
                  type="button"
                  disabled={saving}
                  {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_CUSTOM_OPENER_PATH)}
                  onClick={() => {
                    void pickExecutable("Choose editor executable").then((path) => {
                      if (path) {
                        setDraft((prev) =>
                          prev ? { ...prev, custom_opener_path: path } : prev
                        );
                      }
                    });
                  }}
                >
                  Browse…
                </button>
              </div>
            </div>
          ) : null}

          <CodingAgentsSection
            draft={draft}
            setDraft={setDraft}
            saving={saving}
            setNotice={setNotice}
          />

          <div className="settings-field settings-field--checkbox">
            <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_USAGE_JOURNAL)}>
              <input
                type="checkbox"
                checked={draft.usage_journal_enabled}
                disabled={saving}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, usage_journal_enabled: e.target.checked } : prev
                  )
                }
              />
              Usage journal (local only, no telemetry)
            </label>
          </div>

          <div className="settings-field settings-field--checkbox">
            <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_DEBUG_TIMING)}>
              <input
                type="checkbox"
                checked={draft.debug_timing_enabled}
                disabled={saving}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, debug_timing_enabled: e.target.checked } : prev
                  )
                }
              />
              Debug timing in IPC responses
            </label>
          </div>

          <div className="settings-field settings-field--checkbox">
            <label {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_COMPACT_MODE)}>
              <input
                type="checkbox"
                checked={draft.compact_mode}
                disabled={saving}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, compact_mode: e.target.checked } : prev
                  )
                }
              />
              Compact layout (denser dashboard)
            </label>
          </div>

          <GrafiSection draft={draft} setDraft={setDraft} saving={saving} />

          {/* Sticky so Save and its result are always visible, however far down
              the (long) form the user is — a save error or notice must never be
              off-screen. */}
          <div className="settings-form__footer">
            {settingsError ? (
              <p className="error-text" role="alert">
                {settingsError}
              </p>
            ) : notice ? (
              <p className="settings-field__notice settings-field__notice--ok" role="status">
                {notice}
              </p>
            ) : null}
            {agentSettingsDirty && !saving ? (
              <p className="muted">Unsaved coding agent / opener changes — press Save to apply.</p>
            ) : null}
            <div className="settings-form__actions">
              <button type="submit" disabled={saving} {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_SAVE)}>
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleReset()}
                {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_RESET)}
              >
                Reset defaults
              </button>
            </div>
          </div>
        </form>
      ) : null}

      {settings ? (
        <DataSection
          settings={settings}
          saving={saving}
          onNotice={setNotice}
          onError={setSettingsError}
        />
      ) : null}


      <div className="settings-page__block">
        <h3>About</h3>
        <p className="muted">Graf-Id {__APP_VERSION__} &middot; MIT License</p>
        <p className="muted settings-page__path">github.com/csjozsefdev/Graf-ID</p>
      </div>
    </section>
  );
}
