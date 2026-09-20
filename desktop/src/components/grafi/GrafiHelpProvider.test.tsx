import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import {
  GrafiHelpProvider,
  GRAFI_HELP_HOVER_DELAY_MS,
  GRAFI_HELP_LEAVE_DELAY_MS,
  useGrafiHelp,
} from "./GrafiHelpProvider";
import { GRAFI_HELP_MESSAGES, GRAFI_HELP_TOPIC } from "../../utils/grafiHelpRegistry";
import { DEFAULT_GRAFI_SETTINGS } from "../../utils/grafiSettings";

const loadGrafiSettings = vi.fn(() => ({ ...DEFAULT_GRAFI_SETTINGS }));

vi.mock("../../utils/grafiSettings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../utils/grafiSettings")>();
  return {
    ...actual,
    loadGrafiSettings: () => loadGrafiSettings(),
  };
});

function HelpTopicProbe() {
  const { activeHelpTopic } = useGrafiHelp();
  return <div data-testid="active-help-topic">{activeHelpTopic ?? "none"}</div>;
}

function renderHelpUi(helpingModeEnabled = true) {
  loadGrafiSettings.mockReturnValue({
    ...DEFAULT_GRAFI_SETTINGS,
    helpingModeEnabled,
  });

  return render(
    <GrafiHelpProvider>
      <HelpTopicProbe />
      <button type="button" data-grafi-help={GRAFI_HELP_TOPIC.EXPORT}>
        Export JSON
      </button>
    </GrafiHelpProvider>
  );
}

describe("GrafiHelpProvider", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    loadGrafiSettings.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("activates export help topic on hover when helping mode is enabled", async () => {
    renderHelpUi(true);
    const button = screen.getByRole("button", { name: "Export JSON" });

    await act(async () => {
      fireEvent.mouseOver(button);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(screen.getByTestId("active-help-topic")).toHaveTextContent(GRAFI_HELP_TOPIC.EXPORT);
  });

  it("does not activate help topic on hover when helping mode is disabled", async () => {
    renderHelpUi(false);
    const button = screen.getByRole("button", { name: "Export JSON" });

    await act(async () => {
      fireEvent.mouseOver(button);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(screen.getByTestId("active-help-topic")).toHaveTextContent("none");
  });

  it("shows export help on keyboard focus with aria-describedby", async () => {
    renderHelpUi(true);
    const button = screen.getByRole("button", { name: "Export JSON" });

    await act(async () => {
      fireEvent.focusIn(button);
    });

    expect(screen.getByTestId("active-help-topic")).toHaveTextContent(GRAFI_HELP_TOPIC.EXPORT);
    expect(button).toHaveAttribute(
      "aria-describedby",
      `grafi-help-tooltip-${GRAFI_HELP_TOPIC.EXPORT}`
    );
  });

  it("activates help for dynamically mounted controls", async () => {
    function DynamicHelpControl() {
      const [visible, setVisible] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setVisible(true)}>
            Show control
          </button>
          {visible ? (
            <button type="button" data-grafi-help={GRAFI_HELP_TOPIC.SETTINGS_SAVE}>
              Save settings
            </button>
          ) : null}
        </>
      );
    }

    render(
      <GrafiHelpProvider>
        <HelpTopicProbe />
        <DynamicHelpControl />
      </GrafiHelpProvider>
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Show control" }));
    });

    const saveButton = screen.getByRole("button", { name: "Save settings" });
    await act(async () => {
      fireEvent.mouseOver(saveButton);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });

    expect(screen.getByTestId("active-help-topic")).toHaveTextContent(
      GRAFI_HELP_TOPIC.SETTINGS_SAVE
    );
  });

  it("clears help topic when pointer leaves the element", async () => {
    renderHelpUi(true);
    const button = screen.getByRole("button", { name: "Export JSON" });

    await act(async () => {
      fireEvent.mouseOver(button);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_HOVER_DELAY_MS);
    });
    expect(screen.getByTestId("active-help-topic")).toHaveTextContent(GRAFI_HELP_TOPIC.EXPORT);

    await act(async () => {
      fireEvent.mouseOut(button);
      await vi.advanceTimersByTimeAsync(GRAFI_HELP_LEAVE_DELAY_MS);
    });

    expect(screen.getByTestId("active-help-topic")).toHaveTextContent("none");
  });

  it("does not render Grafi advisor status bubbles", () => {
    renderHelpUi(true);
    expect(document.querySelector(".grafi-advisor")).not.toBeInTheDocument();
    expect(
      screen.queryByText(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.EXPORT])
    ).not.toBeInTheDocument();
  });
});
