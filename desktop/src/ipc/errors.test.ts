import { describe, expect, it } from "vitest";

import { TimeoutError } from "../utils/withTimeout";
import { formatUserError, parseErrorCode } from "./errors";

describe("parseErrorCode", () => {
  it("splits a code: detail formatted message", () => {
    expect(parseErrorCode("project_error: Project not found: 5")).toEqual({
      code: "project_error",
      detail: "Project not found: 5",
    });
  });

  it("falls back to unknown for a plain message", () => {
    expect(parseErrorCode("boom")).toEqual({ code: "unknown", detail: "boom" });
  });
});

describe("formatUserError — timeout mapping (H7/H8)", () => {
  it("maps a withTimeout TimeoutError to the friendly timeout message", () => {
    const err = new TimeoutError("Open Project did not respond in time.");
    const message = formatUserError(err);
    expect(message).toContain("did not respond in time");
    expect(message).toContain("Open Project did not respond in time.");
  });

  it("still produces a readable message for a non-Error thrown value", () => {
    expect(formatUserError("plain string failure")).toContain("plain string failure");
  });

  it("keeps the existing friendly mapping for a known error code unaffected by the new entry", () => {
    const err = new Error("project_error: Project not found: 5");
    expect(formatUserError(err)).toContain(
      "That project was not found in the local registry."
    );
  });
});
