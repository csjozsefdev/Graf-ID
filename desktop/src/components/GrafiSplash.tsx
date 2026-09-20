import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import grafiSplashImg from './grafi-splash.png';
import './GrafiSplash.css';

const GRAFI_SPLASH_DEFAULT_RING_SPIN_DURATION_MS = 1500;
const GRAFI_SPLASH_DEFAULT_RING_IDLE_DURATION_MS = 500;
const GRAFI_SPLASH_DEFAULT_DOTS_INTERVAL_MS = 400;

export interface GrafiSplashProps {
  message?: string;
  visible?: boolean;
  minDurationMs?: number;
  fadeOut?: boolean;
  fadeOutMs?: number;
  ringSpinDurationMs?: number;
  ringIdleDurationMs?: number;
  messageDotsIntervalMs?: number;
  className?: string;
  onHidden?: () => void;
}

type SplashPhase = 'visible' | 'fading' | 'hidden';
type RingPhase = 'spinning' | 'idle';

export function GrafiSplash({
  message = 'Waking up',
  visible = true,
  minDurationMs = 1200,
  fadeOut = true,
  fadeOutMs = 400,
  ringSpinDurationMs = GRAFI_SPLASH_DEFAULT_RING_SPIN_DURATION_MS,
  ringIdleDurationMs = GRAFI_SPLASH_DEFAULT_RING_IDLE_DURATION_MS,
  messageDotsIntervalMs = GRAFI_SPLASH_DEFAULT_DOTS_INTERVAL_MS,
  className,
  onHidden,
}: GrafiSplashProps) {
  const mountTimeRef = useRef(Date.now());
  const overlayRef = useRef<HTMLDivElement>(null);
  const onHiddenCalledRef = useRef(false);
  const isMountedRef = useRef(true);
  const ringIdleTimerRef = useRef<number | null>(null);
  const phaseRef = useRef<SplashPhase>('visible');
  const visibleRef = useRef(visible);

  const [phase, setPhase] = useState<SplashPhase>('visible');
  const [ringPhase, setRingPhase] = useState<RingPhase>('spinning');
  const [spinCycle, setSpinCycle] = useState(0);
  const [dotCount, setDotCount] = useState(0);

  const baseMessage = useMemo(() => message.replace(/\.+$/, '').trim(), [message]);
  const isRingActive = phase === 'visible' && visible;
  const isMessageActive = phase === 'visible';

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (ringIdleTimerRef.current !== null) {
        window.clearTimeout(ringIdleTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!isRingActive) {
      if (ringIdleTimerRef.current !== null) {
        window.clearTimeout(ringIdleTimerRef.current);
        ringIdleTimerRef.current = null;
      }
      return;
    }

    setRingPhase('spinning');
  }, [isRingActive, spinCycle]);

  const handleRingSpinEnd = () => {
    if (!isMountedRef.current || !isRingActive) {
      return;
    }

    setRingPhase('idle');

    if (ringIdleTimerRef.current !== null) {
      window.clearTimeout(ringIdleTimerRef.current);
    }

    ringIdleTimerRef.current = window.setTimeout(() => {
      ringIdleTimerRef.current = null;

      if (
        !isMountedRef.current ||
        phaseRef.current !== 'visible' ||
        !visibleRef.current
      ) {
        return;
      }

      setSpinCycle((cycle) => cycle + 1);
    }, ringIdleDurationMs);
  };

  useEffect(() => {
    if (!isMessageActive || !baseMessage) {
      return;
    }

    const dotsTimer = window.setInterval(() => {
      setDotCount((count) => (count + 1) % 4);
    }, messageDotsIntervalMs);

    return () => {
      window.clearInterval(dotsTimer);
    };
  }, [isMessageActive, baseMessage, messageDotsIntervalMs]);

  // Splash stays visible while visible=true. When the parent sets visible=false,
  // wait only for any remaining minimum display time, then begin hiding.
  useEffect(() => {
    if (visible || phase !== 'visible') {
      return;
    }

    const elapsed = Date.now() - mountTimeRef.current;
    const remainingMinTime = Math.max(0, minDurationMs - elapsed);

    const beginHideTimer = window.setTimeout(() => {
      if (!isMountedRef.current) {
        return;
      }

      if (fadeOut && fadeOutMs > 0) {
        setPhase('fading');
      } else {
        setPhase('hidden');
      }
    }, remainingMinTime);

    return () => {
      window.clearTimeout(beginHideTimer);
    };
  }, [visible, minDurationMs, fadeOut, fadeOutMs, phase]);

  useEffect(() => {
    if (phase !== 'fading') {
      return;
    }

    const overlay = overlayRef.current;
    let finished = false;

    const finishHide = () => {
      if (finished || !isMountedRef.current) {
        return;
      }

      finished = true;
      window.clearTimeout(fallbackTimer);
      overlay?.removeEventListener('transitionend', handleTransitionEnd);
      setPhase('hidden');
    };

    const handleTransitionEnd = (event: TransitionEvent) => {
      if (event.target !== overlay || event.propertyName !== 'opacity') {
        return;
      }

      finishHide();
    };

    const fallbackTimer = window.setTimeout(finishHide, fadeOutMs + 100);
    overlay?.addEventListener('transitionend', handleTransitionEnd);

    return () => {
      finished = true;
      window.clearTimeout(fallbackTimer);
      overlay?.removeEventListener('transitionend', handleTransitionEnd);
    };
  }, [phase, fadeOutMs]);

  useEffect(() => {
    if (phase !== 'hidden' || onHiddenCalledRef.current) {
      return;
    }

    onHiddenCalledRef.current = true;
    onHidden?.();
  }, [phase, onHidden]);

  if (phase === 'hidden') {
    return null;
  }

  const rootClassName = [
    'grafi-splash',
    phase === 'fading' ? 'grafi-splash--fading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const splashStyle = {
    '--grafi-fade-out-ms': `${fadeOutMs}ms`,
    '--grafi-spin-duration': `${ringSpinDurationMs}ms`,
  } as CSSProperties;

  return (
    <div
      ref={overlayRef}
      className={rootClassName}
      style={splashStyle}
      role="status"
      aria-live="polite"
      aria-busy={phase === 'visible'}
    >
      <div className="grafi-splash__content">
        <div className="grafi-splash__visual">
          <img
            className="grafi-splash__image"
            src={grafiSplashImg}
            alt="Grafi startup logo"
            draggable={false}
          />
          <div className="grafi-splash__ring-positioner" aria-hidden="true">
            <div
              key={spinCycle}
              className={[
                'grafi-splash__ring-highlight',
                ringPhase === 'spinning' ? 'grafi-splash__ring-highlight--spinning' : 'grafi-splash__ring-highlight--idle',
              ].join(' ')}
              onAnimationEnd={ringPhase === 'spinning' ? handleRingSpinEnd : undefined}
            />
          </div>
        </div>
        {baseMessage ? (
          <p className="grafi-splash__message" aria-label={baseMessage}>
            <span className="grafi-splash__message-text">{baseMessage}</span>
            <span className="grafi-splash__message-dots" aria-hidden="true">
              {'.'.repeat(dotCount)}
            </span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
