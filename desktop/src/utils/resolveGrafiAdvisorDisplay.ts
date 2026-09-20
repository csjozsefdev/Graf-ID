import type { GrafiSeverity } from "../shared/grafi-advisor";
import { getGrafiHelpMessage } from "./grafiHelpRegistry";

export interface GrafiStatusPresentation {
  message: string | null;
  severity: GrafiSeverity;
}

export interface GrafiAdvisorDisplay {
  message: string | null;
  severity: GrafiSeverity;
  source: "status" | "help" | "none";
}

export function resolveGrafiAdvisorDisplay(input: {
  status: GrafiStatusPresentation;
  activeHelpTopic: string | null;
  helpingModeEnabled: boolean;
  messageDismissed: boolean;
  criticalAlertsOnly?: boolean;
}): GrafiAdvisorDisplay {
  const helpMessage = getGrafiHelpMessage(input.activeHelpTopic);
  const helpActive =
    input.helpingModeEnabled &&
    input.activeHelpTopic !== null &&
    helpMessage !== null &&
    !input.criticalAlertsOnly;

  if (input.status.severity === "critical" && !input.messageDismissed) {
    return {
      message: input.status.message,
      severity: input.status.severity,
      source: "status",
    };
  }

  if (helpActive) {
    return {
      message: helpMessage,
      severity: "info",
      source: "help",
    };
  }

  if (input.messageDismissed) {
    return {
      message: null,
      severity: input.status.severity,
      source: "none",
    };
  }

  return {
    message: input.status.message,
    severity: input.status.severity,
    source: "status",
  };
}
