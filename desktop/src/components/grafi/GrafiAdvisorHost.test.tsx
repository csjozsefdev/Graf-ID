import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GrafiAdvisorHost } from "./GrafiAdvisorHost";
import { GrafiHelpProvider, GRAFI_HELP_HOVER_DELAY_MS } from "./GrafiHelpProvider";
import { GRAFI_HELP_MESSAGES, GRAFI_HELP_TOPIC } from "../../utils/grafiHelpRegistry";
import { GRAFI_HOST_READY_MESSAGE } from "../../utils/grafiAdvisorRules";
import { healthyPanel, healthyProject } from "../../utils/grafiAdvisorTestFixtures";
import { DEFAULT_GRAFI_SETTINGS } from "../../utils/grafiSettings";
import type { DashboardProject, ResumePanelData } from "../../ipc/types";

const loadGrafiSettings = vi.fn(() => ({ ...DEFAULT_GRAFI_SETTINGS }));

vi.mock("../../utils/grafiSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../utils/grafiSettings")>();
  return {
    ...actual,
    loadGrafiSettings: () => loadGrafiSettings(),
  };
});

function renderHost(
  overrides: Partial<{
    nav: "dashboard" | "settings" | "history";
    project: DashboardProject | null;
    panel: ResumePanelData | null;
    projectSelected: boolean;
    detailReady: boolean;
    detailError: string | null;
    onOpenSummary: () => void;
    helpingModeEnabled: boolean;
    enabled: boolean;
    criticalAlertsOnly: boolean;
  }> = {}
) {
  loadGrafiSettings.mockReturnValue({
    ...DEFAULT_GRAFI_SETTINGS,
    enabled: overrides.enabled ?? true,
    helpingModeEnabled: overrides.helpingModeEnabled ?? true,
    criticalAlertsOnly: overrides.criticalAlertsOnly ?? false,
  });

  const onOpenSummary = overrides.onOpenSummary ?? vi.fn();
  const result = render(
    <GrafiHelpProvider>
      <button type="button" data-grafi-help={GRAFI_HELP_TOPIC.EXPORT}>
        Export JSON
      </button>
      <GrafiAdvisorHost
        nav={overrides.nav ?? "dashboard"}
        project={overrides.project ?? healthyProject()}
        panel={overrides.panel ?? healthyPanel()}
        projectSelected={overrides.projectSelected ?? true}
        detailReady={overrides.detailReady ?? true}
        detailError={overrides.detailError ?? null}
        onOpenSummary={onOpenSummary}
      />
    </GrafiHelpProvider>
  );
  return { ...result, onOpenSummary };
}

function grafiRoot(): Element | null {
  return document.querySelector(".grafi-advisor");
}

describe("GrafiAdvisorHost", () => {
  beforeEach(() => {
    loadGrafiSettings.mockReset();
    loadGrafiSettings.mockReturnValue({ ...DEFAULT_GRAFI_SETTINGS });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders Grafi when enabled and project context is ready", () => {
    renderHost();
    expect(grafiRoot()).toBeInTheDocument();
    expect(document.querySelector(".grafi-figure__img")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show Grafi message" })).toBeInTheDocument();
  });

  it("shows contextual tooltip when helping mode is active", async () => {
    vi.useFakeTimers();
    renderHost();

    await act(async () => {
      fireEvent.mouseOver(screen.getByRole("button", { name: "Export JSON" }));
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(document.querySelector(".grafi-context-help")).toBeInTheDocument();
    expect(
      screen.getByText(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.EXPORT])
    ).toBeInTheDocument();
  });

  it("shows Grafi on settings navigation when advisor is enabled", () => {
    const { container } = renderHost({ nav: "settings" });
    expect(document.querySelector(".grafi-advisor")).toBeInTheDocument();
    expect(container.querySelector(".grafi-advisor")).not.toBeInTheDocument();
    expect(document.querySelector("[data-grafi-advisor-portal]")).toBeInTheDocument();
  });

  it("shows warning severity for missing project path", () => {
    const inaccessible = { ...healthyProject(), path_accessible: false };
    renderHost({
      project: inaccessible,
    });
    expect(
      document.querySelector(".grafi-status-badge--warning, .grafi-status-badge--critical")
    ).toBeTruthy();
  });

  it("shows detail load error warning", async () => {
    const user = userEvent.setup();
    renderHost({
      panel: null,
      detailReady: false,
      detailError: "Backend unavailable",
    });
    await user.click(screen.getByRole("button", { name: "Show Grafi message" }));
    expect(screen.getByText(/Could not load project context/i)).toBeInTheDocument();
  });

  it("does not render Grafi when disabled in host settings", () => {
    renderHost({ enabled: false });
    expect(grafiRoot()).not.toBeInTheDocument();
  });

  it("hides non-critical messages when criticalAlertsOnly is enabled", () => {
    renderHost({ criticalAlertsOnly: true });
    expect(grafiRoot()).toBeInTheDocument();
    expect(document.querySelector(".grafi-figure__img")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show Grafi message" })).not.toBeInTheDocument();
    expect(screen.queryByText(GRAFI_HOST_READY_MESSAGE)).not.toBeInTheDocument();
  });

  it("does not render help tooltips when critical alerts only is enabled", async () => {
    vi.useFakeTimers();
    renderHost({ criticalAlertsOnly: true });

    await act(async () => {
      fireEvent.mouseOver(screen.getByRole("button", { name: "Export JSON" }));
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(document.querySelector(".grafi-context-help")).not.toBeInTheDocument();
  });

  it("dismisses the current bubble without globally disabling Grafi", async () => {
    const user = userEvent.setup();
    renderHost();

    await user.click(screen.getByRole("button", { name: "Show Grafi message" }));
    expect(screen.getByText(GRAFI_HOST_READY_MESSAGE)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dismiss Grafi message" }));

    expect(screen.queryByText(GRAFI_HOST_READY_MESSAGE)).not.toBeInTheDocument();
    expect(document.querySelector(".grafi-figure__img")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show Grafi message" })).not.toBeInTheDocument();
  });

  it("emits open-summary to the host handler", async () => {
    const user = userEvent.setup();
    const { onOpenSummary } = renderHost();

    await user.click(screen.getByRole("button", { name: "Show Grafi message" }));
    await user.click(screen.getByRole("button", { name: "Open summary" }));

    expect(onOpenSummary).toHaveBeenCalledTimes(1);
  });

  it("does not render an internal Grafi settings modal", () => {
    renderHost();
    expect(screen.queryByText("Grafi preferences")).not.toBeInTheDocument();
    expect(document.querySelector(".grafi-settings")).not.toBeInTheDocument();
  });
});
