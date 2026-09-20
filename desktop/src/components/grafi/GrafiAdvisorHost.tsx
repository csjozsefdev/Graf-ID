import { useCallback, useEffect, useMemo, useState } from "react";
import { GrafiAdvisor } from "../../shared/grafi-advisor";
import type { GrafiDisplayMode } from "../../shared/grafi-advisor";
import "../../shared/grafi-advisor/grafi.css";
import type { DashboardProject, NavSection, ResumePanelData } from "../../ipc/types";
import {
  GRAFI_SETTINGS_SAVED_EVENT,
  loadGrafiSettings,
} from "../../utils/grafiSettings";
import { getGrafiHelpMessage } from "../../utils/grafiHelpRegistry";
import { resolveGrafiHostPresentation } from "../../utils/grafiAdvisorHost";
import { OPEN_SUMMARY_ACTION, resolveGrafiAdvisorBrief } from "../../utils/grafiAdvisorRules";
import { resolveGrafiAdvisorDisplay } from "../../utils/resolveGrafiAdvisorDisplay";
import { GrafiContextHelpTooltip } from "./GrafiContextHelpTooltip";
import { GrafiAdvisorPortal } from "./GrafiAdvisorPortal";
import { useGrafiHelp } from "./GrafiHelpProvider";

export interface GrafiAdvisorHostProps {
  nav: NavSection;
  project: DashboardProject | null;
  panel: ResumePanelData | null;
  projectSelected: boolean;
  detailReady: boolean;
  detailError?: string | null;
  onOpenSummary: () => void;
}

export function GrafiAdvisorHost({
  nav,
  project,
  panel,
  projectSelected,
  detailReady,
  detailError = null,
  onOpenSummary,
}: GrafiAdvisorHostProps) {
  const { activeHelpTopic, activeHelpRect, helpingModeEnabled } = useGrafiHelp();
  const [settings, setSettings] = useState(loadGrafiSettings);
  const [displayMode, setDisplayMode] = useState<GrafiDisplayMode>("minimized");
  const [messageDismissed, setMessageDismissed] = useState(false);

  const reloadSettings = useCallback(() => {
    setSettings(loadGrafiSettings());
  }, []);

  useEffect(() => {
    window.addEventListener(GRAFI_SETTINGS_SAVED_EVENT, reloadSettings);
    return () => window.removeEventListener(GRAFI_SETTINGS_SAVED_EVENT, reloadSettings);
  }, [reloadSettings]);

  useEffect(() => {
    setMessageDismissed(false);
    setDisplayMode("minimized");
  }, [project?.id, detailReady, nav, detailError]);

  const brief = useMemo(
    () =>
      resolveGrafiAdvisorBrief({
        nav,
        project,
        panel,
        projectSelected,
        detailReady,
        detailError,
      }),
    [nav, project, panel, projectSelected, detailReady, detailError]
  );

  const statusPresentation = useMemo(() => resolveGrafiHostPresentation(brief), [brief]);

  const display = useMemo(
    () =>
      resolveGrafiAdvisorDisplay({
        status: statusPresentation,
        activeHelpTopic: null,
        helpingModeEnabled: false,
        messageDismissed,
        criticalAlertsOnly: settings.criticalAlertsOnly,
      }),
    [statusPresentation, messageDismissed, settings.criticalAlertsOnly]
  );

  const handleAction = useCallback(
    (actionId: string) => {
      if (actionId === OPEN_SUMMARY_ACTION.id) {
        onOpenSummary();
        setDisplayMode("minimized");
      }
    },
    [onOpenSummary]
  );

  const handleDismiss = useCallback(() => {
    setDisplayMode("minimized");
    setMessageDismissed(true);
  }, []);

  const shouldRenderAdvisor = settings.enabled;

  const contextHelpMessage =
    settings.enabled &&
    settings.helpingModeEnabled &&
    helpingModeEnabled &&
    !settings.criticalAlertsOnly &&
    activeHelpTopic
      ? getGrafiHelpMessage(activeHelpTopic)
      : null;

  if (!shouldRenderAdvisor && !contextHelpMessage) {
    return null;
  }

  const showActions = display.message && display.source === "status" && brief?.actions;

  return (
    <>
      {shouldRenderAdvisor ? (
        <GrafiAdvisorPortal>
          <GrafiAdvisor
            appName="Graf-Id"
            severity={display.severity}
            message={display.message}
            context={{ label: "Graf-Id" }}
            settings={settings}
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            onDismiss={handleDismiss}
            onAction={handleAction}
            actions={showActions ? brief?.actions : undefined}
          />
        </GrafiAdvisorPortal>
      ) : null}
      {contextHelpMessage && activeHelpRect && activeHelpTopic ? (
        <GrafiContextHelpTooltip
          topic={activeHelpTopic}
          message={contextHelpMessage}
          anchorRect={activeHelpRect}
        />
      ) : null}
    </>
  );
}
