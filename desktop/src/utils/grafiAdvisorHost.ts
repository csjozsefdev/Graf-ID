import type { GrafiSeverity } from "../shared/grafi-advisor";
import type { GrafiAdvisorBrief } from "./grafiAdvisorRules";
import { formatGrafiHostMessage } from "./grafiAdvisorRules";

export function resolveGrafiHostPresentation(brief: GrafiAdvisorBrief | null): {
  message: string | null;
  severity: GrafiSeverity;
} {
  if (!brief) {
    return { message: null, severity: "info" };
  }
  return {
    message: formatGrafiHostMessage(brief),
    severity: brief.severity,
  };
}
