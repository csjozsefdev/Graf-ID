import { describe, expect, it } from "vitest";
import { resolveGrafiHostPresentation } from "./grafiAdvisorHost";
import { GRAFI_HOST_READY_MESSAGE, resolveGrafiAdvisorBrief } from "./grafiAdvisorRules";
import { healthyPanel, healthyProject } from "./grafiAdvisorTestFixtures";

describe("grafiAdvisorHost", () => {
  it("builds the ready host message from advisor rules for a healthy project", () => {
    const brief = resolveGrafiAdvisorBrief({
      nav: "dashboard",
      project: healthyProject(),
      panel: healthyPanel(),
      projectSelected: true,
      detailReady: true,
    });
    const presentation = resolveGrafiHostPresentation(brief);
    expect(presentation.message).toBe(GRAFI_HOST_READY_MESSAGE);
    expect(
      resolveGrafiAdvisorBrief({
        nav: "dashboard",
        project: healthyProject(),
        panel: healthyPanel(),
        projectSelected: true,
        detailReady: false,
      })
    ).toBeNull();
  });

  it("formats presentation from a warning brief", () => {
    const presentation = resolveGrafiHostPresentation({
      messages: ["Scan issue: timed out. Try Refresh context."],
      severity: "warning",
      actions: [],
    });
    expect(presentation.severity).toBe("warning");
    expect(presentation.message).toContain("Scan issue");
  });

  it("returns null message when brief is null", () => {
    expect(resolveGrafiHostPresentation(null)).toEqual({
      message: null,
      severity: "info",
    });
  });
});
