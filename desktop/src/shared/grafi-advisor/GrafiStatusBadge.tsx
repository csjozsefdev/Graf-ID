import { DEFAULT_GRAFI_MESSAGES } from './defaultMessages';
import type { GrafiSeverity } from './grafiTypes';

const SEVERITY_ICONS: Record<GrafiSeverity, string> = {
  info: 'ℹ',
  success: '✓',
  warning: '!',
  critical: '‼',
};

export interface GrafiStatusBadgeProps {
  severity: GrafiSeverity;
  className?: string;
}

export function GrafiStatusBadge({ severity, className }: GrafiStatusBadgeProps) {
  const label = DEFAULT_GRAFI_MESSAGES.severity[severity];

  return (
    <span
      className={['grafi-status-badge', `grafi-status-badge--${severity}`, className]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="grafi-status-badge__icon" aria-hidden="true">
        {SEVERITY_ICONS[severity]}
      </span>
      <span className="grafi-status-badge__label">{label}</span>
    </span>
  );
}
