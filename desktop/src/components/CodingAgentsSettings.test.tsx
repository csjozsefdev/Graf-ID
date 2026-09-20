import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Settings } from "./Settings";
import { DEFAULT_GRAFI_SETTINGS } from "../utils/grafiSettings";
import type { AppSettingsData, CodingAgentConfig } from "../ipc/types";

function builtins(overrides: Partial<Record<"claude" | "codex", boolean>> = {}): CodingAgentConfig[] {
  return [
    {
      id: "claude-code",
      display_name: "Claude Code",
      executable: "claude",
      args: [],
      built_in: true,
      available: overrides.claude ?? true,
    },
    {
      id: "codex-cli",
      display_name: "Codex CLI",
      executable: "codex",
      args: [],
      built_in: true,
      available: overrides.codex ?? false,
    },
  ];
}

function baseSettings(codingAgents: CodingAgentConfig[] = builtins()): AppSettingsData {
  return {
    data_dir: "C:\\data",
    logs_dir: "C:\\logs",
    config_dir: "C:\\config",
    config_path: "C:\\config\\config.json",
    default_project_opener: "cursor",
    usage_journal_enabled: false,
    debug_timing_enabled: false,
    compact_mode: false,
    opener_options: [
      { id: "system", label: "Auto Detect (System default)" },
      { id: "cursor", label: "Cursor" },
    ],
    python_interpreter_mode: "auto",
    python_interpreter_custom_path: "",
    custom_opener_path: "",
    interpreter_options: [{ id: "auto", label: "Auto Detect" }],
    coding_agents: codingAgents,
  };
}

const fetchAppSettingsMock = vi.fn();
const saveAppSettingsMock = vi.fn();

vi.mock("../utils/grafiSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/grafiSettings")>();
  return { ...actual, loadGrafiSettings: () => ({ ...DEFAULT_GRAFI_SETTINGS }) };
});

vi.mock("../ipc/client", () => ({
  fetchAppSettings: () => fetchAppSettingsMock(),
  saveAppSettings: (input: unknown) => saveAppSettingsMock(input),
  resetAppSettings: vi.fn(),
  openProjectFolderPath: vi.fn(),
  getUserErrorMessage: (err: unknown) => (err instanceof Error ? err.message : String(err)),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

async function renderSettings(settings: AppSettingsData = baseSettings()) {
  fetchAppSettingsMock.mockResolvedValue(settings);
  render(<Settings />);
  await screen.findByLabelText("Open projects with");
}

describe("Settings — Coding Agents (M2/M9/M10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    saveAppSettingsMock.mockImplementation((input: Record<string, unknown>) =>
      Promise.resolve(baseSettings((input.coding_agents as CodingAgentConfig[]) ?? []))
    );
  });

  it("lists built-in agents with Available/Not found status and Edit/Remove controls like any other agent", async () => {
    await renderSettings();

    const claudeRow = screen.getByText("Claude Code", { selector: "strong" }).closest("li")!;
    expect(within(claudeRow).getByText("Available")).toBeInTheDocument();
    expect(within(claudeRow).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(claudeRow).getByRole("button", { name: "Remove" })).toBeInTheDocument();
    expect(within(claudeRow).getByText("Built-in")).toBeInTheDocument();

    const codexRow = screen.getByText("Codex CLI", { selector: "strong" }).closest("li")!;
    expect(within(codexRow).getByText("Not found")).toBeInTheDocument();
  });

  it("an explicit Editor / Coding agent toggle decides which kind of opener Open Project uses", async () => {
    await renderSettings();

    const editorRadio = screen.getByRole("radio", { name: "Editor" });
    const agentRadio = screen.getByRole("radio", { name: "Coding agent" });
    const select = screen.getByLabelText("Open projects with") as HTMLSelectElement;
    const labels = () => Array.from(select.querySelectorAll("option")).map((o) => o.textContent);

    // Editor mode: only editors are offered.
    expect(editorRadio).toHaveAttribute("aria-checked", "true");
    expect(agentRadio).toHaveAttribute("aria-checked", "false");
    expect(labels()).toEqual(["Auto Detect (System default)", "Cursor"]);
    expect(select.value).toBe("cursor");

    // Coding agent mode: only agents; the first available one is preselected and
    // an unavailable one is still offered, labelled honestly.
    fireEvent.click(agentRadio);
    expect(agentRadio).toHaveAttribute("aria-checked", "true");
    expect(labels()).toEqual(["Claude Code", "Codex CLI (not found)"]);
    expect(select.value).toBe("agent:claude-code");

    // Flipping back restores the previous editor choice.
    fireEvent.click(editorRadio);
    expect(select.value).toBe("cursor");

    // The choice is what gets saved.
    fireEvent.click(agentRadio);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    expect(saveAppSettingsMock.mock.calls[0][0].default_project_opener).toBe("agent:claude-code");
  });

  it("the Coding agent option is disabled when no coding agent is configured", async () => {
    await renderSettings(baseSettings([], builtins()));
    expect(screen.getByRole("radio", { name: "Coding agent" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Editor" })).toHaveAttribute("aria-checked", "true");
  });

  it("shows a save error next to the Save button (not off-screen at the top) and flags unsaved agent changes", async () => {
    saveAppSettingsMock.mockRejectedValueOnce(new Error("Claude Code: 'C:\\app' is a directory, not an executable file."));
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "+ Add coding agent" }));
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Claude Code" } });
    fireEvent.change(screen.getByLabelText("Executable"), { target: { value: "C:\\app" } });
    fireEvent.click(screen.getByRole("button", { name: "Add agent" }));

    const saveButton = screen.getByRole("button", { name: "Save" });
    const footer = saveButton.closest(".settings-form__footer") as HTMLElement;
    expect(within(footer).getByText(/Unsaved coding agent/)).toBeInTheDocument();

    fireEvent.click(saveButton);
    await act(async () => {});
    expect(within(footer).getByRole("alert")).toHaveTextContent(/is a directory, not an executable file/);
  });

  it("adds a custom agent as a structured args array, not a raw shell string, and shows it as Pending save until Save", async () => {
    await renderSettings();

    fireEvent.click(screen.getByRole("button", { name: "+ Add coding agent" }));
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "My Tool" } });
    fireEvent.change(screen.getByLabelText("Executable"), { target: { value: "C:\\Tools\\mytool.exe" } });
    fireEvent.change(screen.getByLabelText("Arguments"), {
      target: { value: "--flag\n--value with spaces\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add agent" }));

    const row = screen.getByText("My Tool", { selector: "strong" }).closest("li")!;
    expect(within(row).getByText("Pending save")).toBeInTheDocument();
    expect(within(row).getByText("C:\\Tools\\mytool.exe")).toBeInTheDocument();

    // Not yet selectable as an opener (no stable id until Save assigns one).
    const select = screen.getByLabelText("Open projects with") as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(options).not.toContain("My Tool");

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});

    expect(saveAppSettingsMock).toHaveBeenCalledTimes(1);
    const payload = saveAppSettingsMock.mock.calls[0][0];
    const customEntry = (payload.coding_agents as CodingAgentConfig[]).find(
      (a) => a.display_name === "My Tool"
    );
    expect(customEntry).toMatchObject({
      display_name: "My Tool",
      executable: "C:\\Tools\\mytool.exe",
      args: ["--flag", "--value with spaces"],
      built_in: false,
    });
  });

  it("edits an existing custom agent in place, preserving its id", async () => {
    const custom: CodingAgentConfig = {
      id: "my-tool",
      display_name: "My Tool",
      executable: "mytool",
      args: ["--old"],
      built_in: false,
      available: true,
    };
    await renderSettings(baseSettings([...builtins(), custom]));

    const row = screen.getByText("My Tool", { selector: "strong" }).closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));

    const nameInput = screen.getByLabelText("Display name") as HTMLInputElement;
    expect(nameInput.value).toBe("My Tool");
    fireEvent.change(nameInput, { target: { value: "My Tool Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent" }));

    expect(
      screen.getByText("My Tool Renamed", { selector: "strong" }).closest("li")
    ).toBeInTheDocument();
    expect(screen.queryByText("My Tool", { selector: "strong" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});

    const payload = saveAppSettingsMock.mock.calls[0][0];
    const entries = payload.coding_agents as CodingAgentConfig[];
    expect(entries.filter((a) => !a.built_in)).toHaveLength(1);
    expect(entries.find((a) => !a.built_in)).toMatchObject({ id: "my-tool", display_name: "My Tool Renamed" });
  });

  it("deleting the custom agent currently set as the default opener clears the dangling reference instead of saving it (M9)", async () => {
    const custom: CodingAgentConfig = {
      id: "my-tool",
      display_name: "My Tool",
      executable: "mytool",
      args: [],
      built_in: false,
      available: true,
    };
    const settings = baseSettings([...builtins(), custom]);
    settings.default_project_opener = "agent:my-tool";
    await renderSettings(settings);

    const select = screen.getByLabelText("Open projects with") as HTMLSelectElement;
    expect(select.value).toBe("agent:my-tool");

    const row = screen.getByText("My Tool", { selector: "strong" }).closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    expect(screen.queryByText("My Tool", { selector: "strong" })).not.toBeInTheDocument();
    expect(select.value).not.toBe("agent:my-tool");

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});

    const payload = saveAppSettingsMock.mock.calls[0][0];
    expect(payload.default_project_opener).not.toBe("agent:my-tool");
    expect((payload.coding_agents as CodingAgentConfig[]).some((a) => a.id === "my-tool")).toBe(false);
  });
});
