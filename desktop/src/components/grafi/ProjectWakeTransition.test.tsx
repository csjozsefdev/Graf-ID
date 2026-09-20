import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PROJECT_WAKE_SLOW_STARTUP_MESSAGE } from "./projectWakeMessages";
import { ProjectWakeTransition } from "./ProjectWakeTransition";

vi.mock("../../assets/project-wake-intro.mp4", () => ({
  default: "project-wake-intro.mp4",
}));

function mockVideoElement(video: HTMLVideoElement) {
  Object.defineProperty(video, "duration", {
    configurable: true,
    value: 5,
  });
  video.play = vi.fn().mockResolvedValue(undefined);
}

describe("ProjectWakeTransition", () => {
  it("shows a visible Skip control during the transition", () => {
    render(
      <ProjectWakeTransition
        projectName="Demo"
        visible
        onSkip={vi.fn()}
        onHidden={vi.fn()}
      />
    );

    expect(
      screen.getByRole("button", { name: "Skip project wake transition" })
    ).toBeInTheDocument();
  });

  it("hides the intro video when reduced motion is preferred", () => {
    const matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMedia);

    const { container } = render(
      <ProjectWakeTransition
        projectName="Demo"
        visible
        onSkip={vi.fn()}
        onHidden={vi.fn()}
      />
    );

    expect(container.querySelector(".wake-transition__video--hidden")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("shows slow-startup copy after the first waiting loop completes", () => {
    const { container } = render(
      <ProjectWakeTransition
        projectName="Demo"
        visible
        waitingForEditor
        loopAnimation
        onSkip={vi.fn()}
        onHidden={vi.fn()}
      />
    );

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    mockVideoElement(video!);

    act(() => {
      fireEvent.loadedMetadata(video!);
      fireEvent.ended(video!);
    });

    expect(screen.getByText(PROJECT_WAKE_SLOW_STARTUP_MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("keeps the overlay mounted while waiting for the editor", () => {
    const { rerender, container } = render(
      <ProjectWakeTransition
        projectName="Demo"
        visible
        waitingForEditor
        loopAnimation
        onSkip={vi.fn()}
        onHidden={vi.fn()}
      />
    );

    expect(screen.getByRole("status")).toBeInTheDocument();

    const video = container.querySelector("video");
    mockVideoElement(video!);
    act(() => {
      fireEvent.loadedMetadata(video!);
      fireEvent.ended(video!);
    });

    rerender(
      <ProjectWakeTransition
        projectName="Demo"
        visible
        waitingForEditor
        loopAnimation
        onSkip={vi.fn()}
        onHidden={vi.fn()}
      />
    );

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(PROJECT_WAKE_SLOW_STARTUP_MESSAGE)).toBeInTheDocument();
  });
});
