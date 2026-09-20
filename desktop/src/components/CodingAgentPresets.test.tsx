import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { DEFAULT_GRAFI_SETTINGS } from "../utils/grafiSettings";
import type { AppSettingsData, CodingAgentConfig } from "../ipc/types";

function preset(id: "claude-code" | "codex-cli", over: Partial<CodingAgentConfig> = {}): CodingAgentConfig {
  const isClaude = id === "claude-code";
  return {
    id,
    display_name: isClaude ? "Claude Code" : "Codex CLI",
    executable: isClaude ? "claude" : "codex",
    default_executable: isClaude ? "claude" : "codex",
    executable_override: null,
    args: [],
    built_in: true,
    available: false,
    unavailable_reason: null,
    ...over,
  };
}

function settings(
  agents: CodingAgentConfig[] = [preset("claude-code"), preset("codex-cli")],
  removed: CodingAgentConfig[] = [],
  opener = "cursor"
): AppSettingsData {
  return {
    data_dir: "C:\\data",
    logs_dir: "C:\\logs",
    config_dir: "C:\\config",
    config_path: "C:\\config\\config.json",
    default_project_opener: opener,
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
    coding_agents: agents,
    removed_builtin_agents: removed,
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

async function renderSettings(data: AppSettingsData = settings()) {
  fetchAppSettingsMock.mockResolvedValue(data);
  render(<Settings />);
  await screen.findByLabelText("Open projects with");
}

function rowFor(name: string): HTMLElement {
  return screen.getByText(name, { selector: "strong" }).closest("li") as HTMLElement;
}

function savedPayload() {
  return saveAppSettingsMock.mock.calls[0][0] as {
    default_project_opener: string;
    coding_agents: CodingAgentConfig[];
    removed_builtin_agents: CodingAgentConfig[];
  };
}

describe("Settings — removable built-in coding agent presets with executable override", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    saveAppSettingsMock.mockImplementation((input: Record<string, unknown>) =>
      Promise.resolve({
        ...settings(
          (input.coding_agents as CodingAgentConfig[]) ?? [],
          (input.removed_builtin_agents as CodingAgentConfig[]) ?? [],
          input.default_project_opener as string
        ),
        message: "Settings saved.",
      })
    );
  });

  it("removing a preset hides it from the list and the opener dropdown, saves it as removed, and can be restored", async () => {
    await renderSettings();
    fireEvent.click(within(rowFor("Claude Code")).getByRole("button", { name: "Remove" }));

    expect(screen.queryByText("Claude Code", { selector: "strong" })).not.toBeInTheDocument();
    const select = screen.getByLabelText("Open projects with") as HTMLSelectElement;
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent)).not.toContain(
      "Claude Code (not found)"
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    const payload = savedPayload();
    expect(payload.removed_builtin_agents.map((a) => a.id)).toEqual(["claude-code"]);
    expect(payload.coding_agents.map((a) => a.id)).toEqual(["codex-cli"]);

    fireEvent.click(await screen.findByRole("button", { name: "+ Add preset: Claude Code" }));
    expect(screen.getByText("Claude Code", { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Add preset: Claude Code" })).not.toBeInTheDocument();
  });

  it("removing the preset used as the default opener falls back to Auto Detect and tells the user", async () => {
    await renderSettings(settings(undefined, undefined, "agent:claude-code"));
    const select = screen.getByLabelText("Open projects with") as HTMLSelectElement;
    expect(select.value).toBe("agent:claude-code");

    fireEvent.click(within(rowFor("Claude Code")).getByRole("button", { name: "Remove" }));

    expect(select.value).toBe("system");
    expect(screen.getByRole("status")).toHaveTextContent(/Auto Detect/);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    expect(savedPayload().default_project_opener).toBe("system");
  });

  it("edits a preset's executable override; its display name stays fixed", async () => {
    await renderSettings();
    fireEvent.click(within(rowFor("Codex CLI")).getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("heading", { name: "Edit built-in agent" })).toBeInTheDocument();
    expect((screen.getByLabelText("Display name") as HTMLInputElement).readOnly).toBe(true);
    const exe = screen.getByLabelText("Executable override (optional)") as HTMLInputElement;
    expect(exe.value).toBe("");
    fireEvent.change(exe, { target: { value: "C:\\Tools\\codex.cmd" } });
    fireEvent.change(screen.getByLabelText("Arguments"), { target: { value: "--fast" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent" }));

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    const entry = savedPayload().coding_agents.find((a) => a.id === "codex-cli");
    expect(entry).toMatchObject({
      built_in: true,
      display_name: "Codex CLI",
      executable_override: "C:\\Tools\\codex.cmd",
      args: ["--fast"],
    });
  });

  it("clearing an override goes back to PATH detection", async () => {
    const withOverride = preset("claude-code", {
      executable: "C:\\Tools\\claude.cmd",
      executable_override: "C:\\Tools\\claude.cmd",
      available: true,
    });
    await renderSettings(settings([withOverride, preset("codex-cli")]));

    fireEvent.click(within(rowFor("Claude Code")).getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Executable override (optional)"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save agent" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});

    const entry = savedPayload().coding_agents.find((a) => a.id === "claude-code");
    expect(entry?.executable_override).toBeNull();
    expect(entry?.executable).toBe("claude");
  });

  it("shows why an agent is unavailable, e.g. an invalid override path", async () => {
    const broken = preset("claude-code", {
      executable_override: "C:\\gone\\claude.cmd",
      executable: "C:\\gone\\claude.cmd",
      unavailable_reason: "'C:\\gone\\claude.cmd' does not exist.",
    });
    await renderSettings(settings([broken, preset("codex-cli")]));
    expect(within(rowFor("Claude Code")).getByText(/does not exist\./)).toBeInTheDocument();
  });

  it("surfaces a server-side validation error for a bad override instead of accepting it", async () => {
    saveAppSettingsMock.mockRejectedValueOnce(
      new Error("Claude Code: 'C:\\nope.cmd' does not exist.")
    );
    await renderSettings();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    expect(screen.getByText(/Claude Code: .* does not exist/)).toBeInTheDocument();
  });

  it("reports the backend's fallback notice after saving a removal", async () => {
    saveAppSettingsMock.mockResolvedValueOnce({
      ...settings([preset("codex-cli")], [preset("claude-code")]),
      message: "Settings saved. Opener reset to the default for 1 project(s) that used a removed agent: Alpha.",
    });
    await renderSettings();
    fireEvent.click(within(rowFor("Claude Code")).getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await act(async () => {});
    expect(screen.getByRole("status")).toHaveTextContent(/Opener reset to the default for 1 project/);
  });
});
