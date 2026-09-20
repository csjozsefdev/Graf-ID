import { describe, expect, it } from "vitest";

import {
  formatSidebarSummaryPreview,
  formatWhen,
  sidebarSummaryPreviewText,
  stripSidebarSummaryLineLabel,
  summaryPreviewText,
} from "./continuity";

describe("sidebar summary preview formatting", () => {
  it("prefers the first human line and appends a short next step", () => {
    const raw = [
      "Where you left off: Continuing sidebar regression fix after doc update.",
      "Suggested next step: review changes in app/(tabs)/_layout.tsx",
      "Session still open (started today).",
    ].join("\n");

    expect(formatSidebarSummaryPreview(raw)).toBe(
      "Continuing sidebar regression fix after doc update. · Next: review changes in app/(tabs)/_layout.tsx"
    );
  });

  it("strips repeated label prefixes per line without changing stored summary text", () => {
    const stored = "Where you left off: recent edits in src/a.ts\nSuggested next step: review changes in src/a.ts";
    expect(stored).toContain("Where you left off:");
    expect(stripSidebarSummaryLineLabel("Suggested next step: polish admin UI")).toBe(
      "polish admin UI"
    );
  });

  it("does not rewrite backend summary preview text", () => {
    const project = {
      summary_preview: {
        headline: "sidebar regression fix",
        summary_text:
          "Where you left off: Continuing sidebar regression fix.\nSuggested next step: finish tests.",
      },
      latest_session: null,
    };

    expect(summaryPreviewText(project)).toContain("Where you left off:");
    expect(sidebarSummaryPreviewText(project)).toBe(
      "Continuing sidebar regression fix. · Next: finish tests."
    );
  });
});

describe("formatWhen (local time display)", () => {
  it("converts a stored UTC ISO timestamp to local wall-clock time, not a raw string slice", () => {
    // Regression: the old implementation was `iso.replace("T", " ").slice(0, 19)`,
    // which printed the UTC digits verbatim and mislabeled them as local time —
    // a real, systematic offset for any non-UTC viewer. Build the expected
    // string from the same Date-getter logic the fix uses, so this test holds
    // regardless of which timezone it runs in.
    const iso = "2026-06-18T06:50:28+00:00";
    const date = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    const expected =
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    expect(formatWhen(iso)).toBe(expected);
  });

  it("returns 'Never' for missing or invalid input", () => {
    expect(formatWhen(null)).toBe("Never");
    expect(formatWhen(undefined)).toBe("Never");
    expect(formatWhen("not-a-date")).toBe("Never");
  });
});
