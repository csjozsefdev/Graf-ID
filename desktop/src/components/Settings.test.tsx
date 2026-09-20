import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { GrafiAdvisorHost } from "./grafi/GrafiAdvisorHost";
import {
  GrafiHelpProvider,
  GRAFI_HELP_HOVER_DELAY_MS,
} from "./grafi/GrafiHelpProvider";
import { GrafiContextHelpTooltip } from "./grafi/GrafiContextHelpTooltip";
import { GRAFI_HELP_MESSAGES, GRAFI_HELP_TOPIC } from "../utils/grafiHelpRegistry";
import { DEFAULT_GRAFI_SETTINGS } from "../utils/grafiSettings";
import type { AppSettingsData } from "../ipc/types";

const mockSettings: AppSettingsData = {
  data_dir: "C:\\Users\\demo\\AppData\\Local\\Graf-Id",
  logs_dir: "C:\\Users\\demo\\AppData\\Local\\Graf-Id\\logs",
  config_dir: "C:\\Users\\demo\\AppData\\Local\\Graf-Id",
  config_path: "C:\\Users\\demo\\AppData\\Local\\Graf-Id\\config.json",
  default_project_opener: "cursor",
  usage_journal_enabled: true,
  debug_timing_enabled: false,
  compact_mode: false,
  opener_options: [{ id: "cursor", label: "Cursor" }],
  python_interpreter_mode: "auto",
  python_interpreter_custom_path: "",
  custom_opener_path: "",
  interpreter_options: [{ id: "auto", label: "Auto Detect" }],
};

const loadGrafiSettings = vi.fn(() => ({
  ...DEFAULT_GRAFI_SETTINGS,
  helpingModeEnabled: true,
}));

vi.mock("../utils/grafiSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/grafiSettings")>();
  return {
    ...actual,
    loadGrafiSettings: () => loadGrafiSettings(),
  };
});

vi.mock("../ipc/client", () => ({
  fetchAppSettings: vi.fn(() => Promise.resolve(mockSettings)),
  saveAppSettings: vi.fn(),
  resetAppSettings: vi.fn(),
  openProjectFolderPath: vi.fn(),
  getUserErrorMessage: (err: unknown) => String(err),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
}));

async function renderSettingsShell(helpingModeEnabled = true) {
  loadGrafiSettings.mockReturnValue({
    ...DEFAULT_GRAFI_SETTINGS,
    helpingModeEnabled,
  });

  render(
    <GrafiHelpProvider>
      <main className="app-shell__main" data-testid="settings-scroll">
        <Settings />
      </main>
      <GrafiAdvisorHost
        nav="settings"
        project={null}
        panel={null}
        projectSelected={false}
        detailReady={false}
        onOpenSummary={vi.fn()}
      />
    </GrafiHelpProvider>
  );

  expect(await screen.findByLabelText("Python backend")).toBeInTheDocument();
}

describe("Settings helping mode regressions", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps Grafi visible after scrolling the settings page", async () => {
    await renderSettingsShell(true);

    expect(document.querySelector(".grafi-advisor")).toBeInTheDocument();
    expect(document.querySelector("[data-grafi-advisor-portal]")).toBeInTheDocument();

    const scrollContainer = screen.getByTestId("settings-scroll");
    scrollContainer.scrollTop = 1200;

    fireEvent.scroll(scrollContainer);

    expect(document.querySelector(".grafi-advisor")).toBeInTheDocument();
  });

  it("shows a settings-specific tooltip when Helping Mode is enabled", async () => {
    await renderSettingsShell(true);

    vi.useFakeTimers();
    const checkbox = screen.getByLabelText("Usage journal (local only, no telemetry)");
    const helpHost = checkbox.closest("label");
    expect(helpHost).not.toBeNull();

    await act(async () => {
      fireEvent.mouseOver(checkbox);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(document.querySelector(".grafi-context-help")).toBeInTheDocument();
    expect(
      screen.getByText(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.SETTINGS_USAGE_JOURNAL])
    ).toBeInTheDocument();
    expect(helpHost).toHaveAttribute(
      "aria-describedby",
      `grafi-help-tooltip-${GRAFI_HELP_TOPIC.SETTINGS_USAGE_JOURNAL}`
    );
  });

  it("does not show settings tooltips when Helping Mode is disabled", async () => {
    await renderSettingsShell(false);

    vi.useFakeTimers();
    const checkbox = screen.getByLabelText("Usage journal (local only, no telemetry)");
    const helpHost = checkbox.closest("label");
    expect(helpHost).not.toBeNull();

    await act(async () => {
      fireEvent.mouseOver(checkbox);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(document.querySelector(".grafi-context-help")).not.toBeInTheDocument();
    expect(helpHost).not.toHaveAttribute("aria-describedby");
  });

  it("shows settings help on keyboard focus", async () => {
    await renderSettingsShell(true);

    const saveButton = screen.getByRole("button", { name: "Save" });

    await act(async () => {
      fireEvent.focusIn(saveButton);
    });

    expect(
      screen.getByText(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.SETTINGS_SAVE])
    ).toBeInTheDocument();
    expect(saveButton).toHaveAttribute(
      "aria-describedby",
      `grafi-help-tooltip-${GRAFI_HELP_TOPIC.SETTINGS_SAVE}`
    );
  });
});

describe("GrafiContextHelpTooltip", () => {
  it("renders with an id for aria-describedby", () => {
    render(
      <GrafiContextHelpTooltip
        topic={GRAFI_HELP_TOPIC.SETTINGS_SAVE}
        message="Save settings"
        anchorRect={
          {
            top: 10,
            left: 10,
            right: 120,
            bottom: 30,
            width: 110,
            height: 20,
            x: 10,
            y: 10,
            toJSON: () => ({}),
          } as DOMRect
        }
      />
    );

    expect(document.getElementById(`grafi-help-tooltip-${GRAFI_HELP_TOPIC.SETTINGS_SAVE}`)).toBeInTheDocument();
  });
});
