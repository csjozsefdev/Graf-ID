import { DEFAULT_GRAFI_MESSAGES } from './defaultMessages';
import { GrafiBubble } from './GrafiBubble';
import { isMessageVisible } from './messageVisibility';
import type { GrafiAdvisorProps } from './grafiTypes';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';
import './grafi.css';

export function GrafiAdvisor({
  appName,
  context,
  severity,
  message,
  actions,
  settings,
  displayMode = 'minimized',
  onDisplayModeChange,
  onDismiss,
  onAction,
  className,
  placement = 'bottom-left',
}: GrafiAdvisorProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const messageAllowed =
    !(settings.criticalAlertsOnly && severity !== 'critical');
  const effectiveMessage =
    messageAllowed && isMessageVisible(message) ? message : null;
  const hasMessage = isMessageVisible(effectiveMessage);

  const showAdvisor = settings.enabled;

  const motionAllowed = settings.motionEnabled && !prefersReducedMotion;
  const showBubble = displayMode === 'expanded' && hasMessage;

  if (!showAdvisor) {
    return null;
  }

  const handleDismiss = () => {
    if (onDismiss) {
      onDismiss();
    } else {
      onDisplayModeChange?.('minimized');
    }
  };

  const handleExpand = () => {
    if (hasMessage) {
      onDisplayModeChange?.('expanded');
    }
  };

  const rootClassName = [
    'grafi-advisor',
    `grafi-advisor--${severity}`,
    `grafi-advisor--placement-${placement}`,
    showBubble ? 'grafi-advisor--expanded' : 'grafi-advisor--minimized',
    motionAllowed ? 'grafi-advisor--motion' : 'grafi-advisor--motion-off',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className={rootClassName} aria-label={`${DEFAULT_GRAFI_MESSAGES.advisorLabel} — ${appName}`}>
      <GrafiBubble
        severity={severity}
        message={effectiveMessage}
        context={context}
        actions={actions}
        displayMode={displayMode}
        motionEnabled={motionAllowed}
        onAction={onAction}
        onDismiss={handleDismiss}
        onExpand={handleExpand}
      />
    </section>
  );
}
