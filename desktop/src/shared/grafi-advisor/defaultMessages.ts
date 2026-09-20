import type { GrafiSeverity } from './grafiTypes';

export const DEFAULT_GRAFI_MESSAGES = {
  expand: 'Expand',
  minimize: 'Minimize',
  settings: 'Settings',
  hostSettingsSectionTitle: 'Grafi preferences',
  hostSettingsSectionHint: 'Configure Grafi from your application settings.',
  dismiss: 'Dismiss',
  dismissMessage: 'Dismiss Grafi message',
  showMessage: 'Show Grafi message',
  severity: {
    info: 'Info',
    success: 'Success',
    warning: 'Warning',
    critical: 'Critical',
  } satisfies Record<GrafiSeverity, string>,
  settingsLabels: {
    enabled: 'Show Grafi advisor',
    motionEnabled: 'Enable motion',
    criticalAlertsOnly: 'Critical alerts only',
  },
  advisorLabel: 'Grafi advisor',
} as const;
