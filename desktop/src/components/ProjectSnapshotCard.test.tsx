import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProjectSnapshotCard } from "./ProjectSnapshotCard";
import { hasProjectSnapshot, snapshotCoveredSections, snapshotSubsections } from "../utils/projectSnapshot";

const full = {
  current_focus: ["Checkout flow is finished."],
  open_issues: ["Waiting for the API key", "Refund flow"],
  recent_fixes: ["Pin release runtime to Python 3.12.10"],
  recent_improvements: ["Add integration flow tracing"],
  suggested_next_step: "Wire the receipt page",
};

describe("ProjectSnapshotCard", () => {
  it("shows the five snapshot sections", () => {
    render(<ProjectSnapshotCard snapshot={full} />);
    const card = screen.getByLabelText("Project Snapshot");
    for (const title of [
      "Current focus",
      "Open issues / blockers",
      "Recent fixes",
      "Recent improvements",
      "Suggested next step",
    ]) {
      expect(within(card).getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(within(card).getByText("Refund flow")).toBeInTheDocument();
    expect(within(card).getByText("Wire the receipt page")).toBeInTheDocument();
  });

  it("omits empty sections and renders nothing at all when there is nothing reliable", () => {
    const { container, rerender } = render(
      <ProjectSnapshotCard snapshot={{ recent_fixes: ["Fix one thing"], open_issues: [] }} />
    );
    expect(screen.getByRole("heading", { name: "Recent fixes" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Open issues / blockers" })).not.toBeInTheDocument();
    rerender(<ProjectSnapshotCard snapshot={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ProjectSnapshotCard snapshot={{ current_focus: [], suggested_next_step: "  " }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ignores non-string junk defensively", () => {
    const junk = { recent_fixes: [1, null, "Real fix"] } as unknown as Parameters<typeof snapshotSubsections>[0];
    expect(snapshotSubsections(junk)[0].items).toEqual(["Real fix"]);
    expect(hasProjectSnapshot(undefined)).toBe(false);
  });

  it("reports the sections it covers so the panel does not repeat them", () => {
    expect(snapshotCoveredSections(full)).toEqual([
      { title: "Suggested next step", body: "Wire the receipt page" },
      { title: "Blocker", body: "Waiting for the API key" },
      { title: "Blocker", body: "Refund flow" },
    ]);
  });
});
