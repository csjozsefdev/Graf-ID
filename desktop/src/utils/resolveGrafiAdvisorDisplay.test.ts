import { describe, expect, it } from "vitest";
import { GRAFI_HELP_MESSAGES, GRAFI_HELP_TOPIC } from "./grafiHelpRegistry";
import { resolveGrafiAdvisorDisplay } from "./resolveGrafiAdvisorDisplay";

describe("resolveGrafiAdvisorDisplay", () => {
  it("shows help message when helping mode is on and a topic is active", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Project context is ready.", severity: "info" },
      activeHelpTopic: GRAFI_HELP_TOPIC.EXPORT,
      helpingModeEnabled: true,
      messageDismissed: false,
    });
    expect(result.source).toBe("help");
    expect(result.message).toBe(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.EXPORT]);
  });

  it("does not show help when helping mode is disabled", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Project context is ready.", severity: "info" },
      activeHelpTopic: GRAFI_HELP_TOPIC.EXPORT,
      helpingModeEnabled: false,
      messageDismissed: false,
    });
    expect(result.source).toBe("status");
    expect(result.message).toBe("Project context is ready.");
  });

  it("prioritizes critical status over help tips", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Folder missing.", severity: "critical" },
      activeHelpTopic: GRAFI_HELP_TOPIC.EXPORT,
      helpingModeEnabled: true,
      messageDismissed: false,
    });
    expect(result.source).toBe("status");
    expect(result.message).toBe("Folder missing.");
  });

  it("allows help after a dismissed status message", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Project context is ready.", severity: "info" },
      activeHelpTopic: GRAFI_HELP_TOPIC.REFRESH_CONTEXT,
      helpingModeEnabled: true,
      messageDismissed: true,
    });
    expect(result.source).toBe("help");
    expect(result.message).toBe(GRAFI_HELP_MESSAGES[GRAFI_HELP_TOPIC.REFRESH_CONTEXT]);
  });

  it("restores status message when help topic clears", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Project context is ready.", severity: "info" },
      activeHelpTopic: null,
      helpingModeEnabled: true,
      messageDismissed: false,
    });
    expect(result.source).toBe("status");
    expect(result.message).toBe("Project context is ready.");
  });

  it("suppresses help tips when critical alerts only is enabled", () => {
    const result = resolveGrafiAdvisorDisplay({
      status: { message: "Project context is ready.", severity: "info" },
      activeHelpTopic: GRAFI_HELP_TOPIC.EXPORT,
      helpingModeEnabled: true,
      messageDismissed: false,
      criticalAlertsOnly: true,
    });
    expect(result.source).toBe("status");
    expect(result.message).toBe("Project context is ready.");
  });
});
