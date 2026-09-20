import { DEFAULT_GRAFI_MESSAGES } from './defaultMessages';
import { GrafiFigure } from './GrafiFigure';
import { isMessageVisible } from './messageVisibility';
import { GrafiStatusBadge } from './GrafiStatusBadge';
import type {
  GrafiAction,
  GrafiDisplayContext,
  GrafiDisplayMode,
  GrafiSeverity,
} from './grafiTypes';
import type { ReactNode } from 'react';

export interface GrafiBubbleProps {
  severity: GrafiSeverity;
  message?: ReactNode | null;
  context?: GrafiDisplayContext;
  actions?: GrafiAction[];
  displayMode: GrafiDisplayMode;
  motionEnabled?: boolean;
  onAction?: (actionId: string) => void;
  onDismiss?: () => void;
  onExpand?: () => void;
}

export function GrafiBubble({
  severity,
  message,
  context,
  actions,
  displayMode,
  motionEnabled = true,
  onAction,
  onDismiss,
  onExpand,
}: GrafiBubbleProps) {
  const hasMessage = isMessageVisible(message);
  const showBubble = displayMode === 'expanded' && hasMessage;
  const messageRole = severity === 'critical' ? 'alert' : 'status';
  const figureSize = showBubble ? 'default' : 'compact';

  const figure = (
    <GrafiFigure
      motionEnabled={motionEnabled}
      size={figureSize}
      decorative={!showBubble && hasMessage}
    />
  );

  return (
    <div
      className={[
        'grafi-bubble',
        showBubble ? 'grafi-bubble--expanded' : 'grafi-bubble--minimized',
      ].join(' ')}
    >
      <div className="grafi-bubble__figure-column">
        {!showBubble && hasMessage ? (
          <button
            type="button"
            className="grafi-bubble__figure-btn"
            aria-label={DEFAULT_GRAFI_MESSAGES.showMessage}
            aria-expanded={false}
            onClick={onExpand}
          >
            {figure}
          </button>
        ) : (
          <div className="grafi-bubble__figure-wrap">{figure}</div>
        )}
        {!showBubble ? (
          <div className="grafi-bubble__figure-meta">
            <GrafiStatusBadge severity={severity} />
          </div>
        ) : null}
      </div>

      {showBubble ? (
        <div className="grafi-bubble__panel">
          <div className="grafi-bubble__panel-header">
            <GrafiStatusBadge severity={severity} />
            <button
              type="button"
              className="grafi-bubble__dismiss"
              aria-label={DEFAULT_GRAFI_MESSAGES.dismissMessage}
              onClick={onDismiss}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
          {context?.label ? (
            <p className="grafi-bubble__context-label">{context.label}</p>
          ) : null}
          {context?.detail ? (
            <p className="grafi-bubble__context-detail">{context.detail}</p>
          ) : null}
          <p className="grafi-bubble__message" role={messageRole}>
            {message}
          </p>
          {actions && actions.length > 0 ? (
            <div className="grafi-bubble__actions">
              {actions.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  className={[
                    'grafi-bubble__action',
                    action.variant ? `grafi-bubble__action--${action.variant}` : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  disabled={action.disabled}
                  aria-label={action.ariaLabel ?? action.label}
                  onClick={() => onAction?.(action.id)}
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
