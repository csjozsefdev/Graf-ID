import { describe, expect, it } from "vitest";

import {
  layoutResumeSections,
  partitionMvpSections,
  sessionFieldsDuplicatedInSections,
} from "./resumeSections";

describe("layoutResumeSections", () => {
  const sections = [
    { title: "Where you left off", body: "Checkout finished" },
    { title: "Suggested next step", body: "Wire the receipt page" },
    { title: "Blocker", body: "Waiting for the API key" },
    { title: "Notes on file", body: "Client prefers weekly summaries" },
    { title: "Recent file changes", body: "a.ts\nb.ts" },
    { title: "Code markers (detail)", body: "Open markers in x.ts" },
    { title: "Session", body: "Ended yesterday" },
    { title: "Context", body: "Confidence: medium" },
  ];

  it("splits Where you left off, lead fallbacks and technical evidence", () => {
    const { whereLeftOff, lead, evidence } = layoutResumeSections(sections);
    expect(whereLeftOff?.body).toBe("Checkout finished");
    expect(lead.map((s) => s.title)).toEqual(["Suggested next step", "Blocker"]);
    expect(evidence.map((s) => s.title)).toEqual([
      "Notes on file",
      "Recent file changes",
      "Code markers (detail)",
      "Session",
      "Context",
    ]);
  });

  it("drops next step / blocker sections the Project Snapshot already shows", () => {
    const covered = [
      { title: "Suggested next step", body: "Wire the receipt page" },
      { title: "Blocker", body: "Waiting for the API key" },
    ];
    expect(layoutResumeSections(sections, covered).lead).toEqual([]);
  });

  it("keeps a fallback next step the snapshot does not contain", () => {
    const covered = [{ title: "Blocker", body: "Waiting for the API key" }];
    expect(layoutResumeSections(sections, covered).lead.map((s) => s.title)).toEqual([
      "Suggested next step",
    ]);
  });

  it("handles an empty section list", () => {
    expect(layoutResumeSections([])).toEqual({ whereLeftOff: null, lead: [], evidence: [] });
  });
});

describe("partitionMvpSections", () => {
  it("orders primary continuity sections first", () => {
    const sections = [
      { title: "Session", body: "Ended yesterday" },
      { title: "Where you left off", body: "Ship polish" },
      { title: "Notes on file", body: "See HANDOFF" },
    ];
    const { primary, secondary } = partitionMvpSections(sections);
    expect(primary.map((section) => section.title)).toEqual([
      "Where you left off",
      "Notes on file",
    ]);
    expect(secondary.map((section) => section.title)).toEqual(["Session"]);
  });

  it("puts unknown sections in secondary bucket", () => {
    const sections = [
      { title: "Where you left off", body: "A" },
      { title: "Custom section", body: "B" },
    ];
    const { primary, secondary } = partitionMvpSections(sections);
    expect(primary).toHaveLength(1);
    expect(secondary).toHaveLength(1);
    expect(secondary[0]?.title).toBe("Custom section");
  });
});

describe("sessionFieldsDuplicatedInSections", () => {
  it("hides grid fields already present in MVP sections", () => {
    const sections = [
      { title: "Blocker", body: "Waiting on API" },
      { title: "Suggested next step", body: "Write tests" },
    ];
    const result = sessionFieldsDuplicatedInSections(sections, {
      blocker: "Waiting on API",
      nextStep: "Write tests",
      exitNote: "Done for today",
    });
    expect(result.showBlocker).toBe(false);
    expect(result.showNextStep).toBe(false);
    expect(result.showExitNote).toBe(true);
  });
});
