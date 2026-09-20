import type { ReactNode } from 'react';

export type GrafiSeverity = 'info' | 'success' | 'warning' | 'critical';

export type GrafiDisplayMode = 'minimized' | 'expanded';

/** Fixed screen placement. Default ecosystem convention is bottom-left. */
type GrafiPlacement = 'bottom-left' | 'static';

export interface GrafiSettings {
  enabled: boolean;
  motionEnabled: boolean;
  criticalAlertsOnly: boolean;
  helpingModeEnabled: boolean;
}

export interface GrafiAction {
  id: string;
  label: string;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  ariaLabel?: string;
}

export interface GrafiDisplayContext {
  label?: string;
  detail?: string;
}

export interface GrafiAdvisorProps {
  appName: string;
  context?: GrafiDisplayContext;
  severity: GrafiSeverity;
  message?: ReactNode | null;
  actions?: GrafiAction[];
  settings: GrafiSettings;
  displayMode?: GrafiDisplayMode;
  onDisplayModeChange?: (mode: GrafiDisplayMode) => void;
  onDismiss?: () => void;
  onAction?: (actionId: string) => void;
  className?: string;
  /** @internal Non-default placement for tests or embedded previews. Defaults to bottom-left. */
  placement?: GrafiPlacement;
}
