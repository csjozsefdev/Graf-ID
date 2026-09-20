import { useState } from "react";
import type { CodingAgentConfig } from "../../ipc/types";
import { openerValueForAgent } from "../../utils/codingAgents";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../../utils/grafiHelpRegistry";
import { pickExecutable } from "./settingsDraft";
import type { AgentFormDraft, SetDraft, SettingsDraft } from "./settingsDraft";

interface CodingAgentsSectionProps {
  draft: SettingsDraft;
  setDraft: SetDraft;
  saving: boolean;
  setNotice: (notice: string | null) => void;
}

/** Coding agents: the editable list (built-in presets + custom agents) and the add/edit form. */
export function CodingAgentsSection({ draft, setDraft, saving, setNotice }: CodingAgentsSectionProps) {
  const [agentForm, setAgentForm] = useState<AgentFormDraft | null>(null);
  const [agentFormMode, setAgentFormMode] = useState<"add" | "edit">("add");
  const [agentFormError, setAgentFormError] = useState<string | null>(null);

  const openAddAgentForm = () => {
    setAgentFormMode("add");
    setAgentForm({ builtIn: false, id: "", display_name: "", executable: "", argsText: "" });
    setAgentFormError(null);
  };

  const openEditAgentForm = (agent: CodingAgentConfig) => {
    setAgentFormMode("edit");
    setAgentForm({
      builtIn: agent.built_in,
      id: agent.id,
      display_name: agent.display_name,
      // For a built-in this is the optional override only; empty means "detect on PATH".
      executable: agent.built_in ? (agent.executable_override ?? "") : agent.executable,
      argsText: agent.args.join("\n"),
    });
    setAgentFormError(null);
  };

  const closeAgentForm = () => {
    setAgentForm(null);
    setAgentFormError(null);
  };

  const handleAgentFormSave = () => {
    if (!agentForm) return;
    const displayName = agentForm.display_name.trim();
    const executable = agentForm.executable.trim();
    if (!agentForm.builtIn) {
      if (!displayName) {
        setAgentFormError("Display name is required.");
        return;
      }
      if (!executable) {
        setAgentFormError("Executable is required.");
        return;
      }
    }
    const args = agentForm.argsText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);

    setDraft((prev) => {
      if (!prev) return prev;
      if (agentFormMode === "edit") {
        const codingAgents = prev.codingAgents.map((a) => {
          if (a.id !== agentForm.id) return a;
          if (a.built_in) {
            return {
              ...a,
              executable_override: executable || null,
              executable: executable || a.default_executable || a.executable,
              args,
            };
          }
          return { ...a, display_name: displayName, executable, args };
        });
        return { ...prev, codingAgents };
      }
      const newAgent: CodingAgentConfig = {
        id: "",
        display_name: displayName,
        executable,
        args,
        built_in: false,
        available: false,
      };
      return { ...prev, codingAgents: [...prev.codingAgents, newAgent] };
    });
    closeAgentForm();
  };

  // Removing works the same for built-in presets and custom agents. A removed
  // preset stays defined in code (so it keeps updating with new versions) and
  // is only marked hidden in config; it can be restored below the list.
  const handleRemoveAgent = (agent: CodingAgentConfig) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const codingAgents = prev.codingAgents.filter((a) => a.id !== agent.id);
      const removedBuiltinAgents = agent.built_in
        ? [
            ...prev.removedBuiltinAgents,
            {
              ...agent,
              executable: agent.default_executable ?? agent.executable,
              executable_override: null,
              args: [],
            },
          ]
        : prev.removedBuiltinAgents;
      // A removed agent must never leave a dangling opener reference.
      const usedAsDefault = prev.default_project_opener === openerValueForAgent(agent.id);
      return {
        ...prev,
        codingAgents,
        removedBuiltinAgents,
        default_project_opener: usedAsDefault ? "system" : prev.default_project_opener,
      };
    });
    setAgentForm((prev) => (prev && prev.id === agent.id ? null : prev));
    setNotice(
      draft?.default_project_opener === openerValueForAgent(agent.id)
        ? `${agent.display_name} was your default opener — it will fall back to Auto Detect. Save to apply.`
        : `${agent.display_name} removed. Save to apply; any project opener using it will reset to the default.`
    );
  };

  const handleRestorePreset = (agent: CodingAgentConfig) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const firstCustom = prev.codingAgents.findIndex((a) => !a.built_in);
      const at = firstCustom === -1 ? prev.codingAgents.length : firstCustom;
      const codingAgents = [...prev.codingAgents];
      codingAgents.splice(at, 0, agent);
      return {
        ...prev,
        codingAgents,
        removedBuiltinAgents: prev.removedBuiltinAgents.filter((a) => a.id !== agent.id),
      };
    });
  };

  return (
    <div
      className="settings-field"
      {...grafiHelpProps(GRAFI_HELP_TOPIC.SETTINGS_CODING_AGENTS)}
    >
      <span className="settings-field__label">Coding agents</span>
      <p className="muted settings-field__hint">
        Claude Code and Codex CLI are offered as presets — remove the ones you don't use,
        or point them at an explicit executable path. Add any other interactive CLI tool as
        a custom agent. Graf-Id only launches agents in the project folder and does not
        track or manage their sessions.
      </p>

      {draft.codingAgents.length > 0 ? (
        <ul className="coding-agents-list">
          {draft.codingAgents.map((agent) => (
            <li key={agent.id || `new:${agent.display_name}`} className="coding-agents-list__item">
              <div className="coding-agents-list__info">
                <strong>{agent.display_name}</strong>{" "}
                <span className="muted">{agent.executable}</span>
                {agent.args.length > 0 ? (
                  <span className="muted"> {agent.args.join(" ")}</span>
                ) : null}
                {agent.id !== "" && !agent.available && agent.unavailable_reason ? (
                  <div className="muted coding-agents-list__reason">
                    {agent.unavailable_reason}
                  </div>
                ) : null}
              </div>
              <span
                className={
                  "coding-agents-list__status" +
                  (agent.id === ""
                    ? ""
                    : agent.available
                      ? " coding-agents-list__status--ok"
                      : " coding-agents-list__status--warn")
                }
              >
                {agent.id === "" ? "Pending save" : agent.available ? "Available" : "Not found"}
              </span>
              {agent.built_in ? <span className="muted">Built-in</span> : null}
              <div className="settings-form__actions">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => openEditAgentForm(agent)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleRemoveAgent(agent)}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="settings-form__actions">
        <button type="button" disabled={saving} onClick={openAddAgentForm}>
          + Add coding agent
        </button>
        {draft.removedBuiltinAgents.map((preset) => (
          <button
            key={preset.id}
            type="button"
            disabled={saving}
            onClick={() => handleRestorePreset(preset)}
          >
            {`+ Add preset: ${preset.display_name}`}
          </button>
        ))}
      </div>

      {agentForm ? (
        <div className="settings-page__block">
          <h4>
            {agentFormMode === "add"
              ? "Add coding agent"
              : agentForm.builtIn
                ? "Edit built-in agent"
                : "Edit coding agent"}
          </h4>
          {agentFormError ? <p className="error-text">{agentFormError}</p> : null}
          <div className="settings-field">
            <label className="settings-field__label" htmlFor="agent-display-name">
              Display name
            </label>
            <input
              id="agent-display-name"
              className="settings-field__input"
              type="text"
              value={agentForm.display_name}
              readOnly={agentForm.builtIn}
              onChange={(e) =>
                setAgentForm((prev) => (prev ? { ...prev, display_name: e.target.value } : prev))
              }
            />
          </div>
          <div className="settings-field">
            <label className="settings-field__label" htmlFor="agent-executable">
              {agentForm.builtIn ? "Executable override (optional)" : "Executable"}
            </label>
            <div className="settings-field__path-row">
              <input
                id="agent-executable"
                className="settings-field__input"
                type="text"
                value={agentForm.executable}
                placeholder={
                  agentForm.builtIn
                    ? "Leave empty to detect on PATH, or C:\\path\\to\\tool.cmd"
                    : "mytool or C:\\path\\to\\agent.exe"
                }
                onChange={(e) =>
                  setAgentForm((prev) => (prev ? { ...prev, executable: e.target.value } : prev))
                }
              />
              <button
                type="button"
                onClick={() => {
                  void pickExecutable("Choose agent executable").then((path) => {
                    if (path) {
                      setAgentForm((prev) => (prev ? { ...prev, executable: path } : prev));
                    }
                  });
                }}
              >
                Browse…
              </button>
            </div>
            <p className="muted settings-field__hint">
              {agentForm.builtIn
                ? "An explicit path takes priority over PATH detection and is never silently replaced by it. It must exist, be a file (not a folder) and be an .exe, .cmd, .bat or .com."
                : "A bare command resolved on PATH, or an explicit path to the executable."}
            </p>
          </div>
          <div className="settings-field">
            <label className="settings-field__label" htmlFor="agent-args">
              Arguments
            </label>
            <textarea
              id="agent-args"
              className="settings-field__input"
              rows={3}
              value={agentForm.argsText}
              placeholder={"One argument per line"}
              onChange={(e) =>
                setAgentForm((prev) => (prev ? { ...prev, argsText: e.target.value } : prev))
              }
            />
            <p className="muted settings-field__hint">
              One argument per line. Each line is passed to the agent exactly as written —
              no shell quoting is applied, so spaces inside a line do not need escaping.
            </p>
          </div>
          <div className="settings-form__actions">
            <button type="button" onClick={handleAgentFormSave}>
              {agentFormMode === "add" ? "Add agent" : "Save agent"}
            </button>
            <button type="button" onClick={closeAgentForm}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <p className="muted settings-field__hint">
        Availability is rechecked whenever Settings loads or saves. Save to apply agent
        changes (a new agent gets its id when saved). Removing an agent that is used as an
        opener resets that opener to the default.
      </p>
    </div>
  );
}
