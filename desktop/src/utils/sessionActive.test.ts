import { describe, expect, it } from "vitest";

import { projectHasOpenSession } from "./sessionActive";

describe("projectHasOpenSession", () => {
  it("returns true when has_open_session flag is set", () => {
    expect(
      projectHasOpenSession({
        has_open_session: true,
        latest_session: null,
      })
    ).toBe(true);
  });

  it("returns true when latest session is active", () => {
    expect(
      projectHasOpenSession({
        has_open_session: false,
        latest_session: {
          id: 1,
          started_at: "2026-06-08T10:00:00+00:00",
          ended_at: null,
          is_active: true,
          status: "active",
          summary: null,
          exit_note: null,
          blocker: null,
          next_step: null,
        },
      })
    ).toBe(true);
  });

  it("returns false when session ended", () => {
    expect(
      projectHasOpenSession({
        has_open_session: false,
        latest_session: {
          id: 1,
          started_at: "2026-06-08T10:00:00+00:00",
          ended_at: "2026-06-08T12:00:00+00:00",
          is_active: false,
          status: "completed",
          summary: null,
          exit_note: "Done",
          blocker: null,
          next_step: null,
        },
      })
    ).toBe(false);
  });
});
