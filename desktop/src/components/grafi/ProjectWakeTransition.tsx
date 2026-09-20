import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import projectWakeIntroVideo from "../../assets/project-wake-intro.mp4";

import {
  PROJECT_WAKE_SLOW_STARTUP_MESSAGE,
  PROJECT_WAKE_TERMINAL_LINES,
  PROJECT_WAKE_VIDEO_CYCLE_FALLBACK_MS,
} from "./projectWakeMessages";
import { getVisibleTerminalLineCountLooping } from "../../utils/projectWakeTiming";

import "./ProjectWakeTransition.css";

export interface ProjectWakeTransitionProps {
  projectName: string;
  visible: boolean;
  revealAllLines?: boolean;
  waitingForEditor?: boolean;
  loopAnimation?: boolean;
  fadeInMs?: number;
  fadeOutMs?: number;
  onSkip: () => void;
  onHidden: () => void;
}

type TransitionPhase = "entering" | "visible" | "fading" | "hidden";

function readReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function clampFadeMs(value: number | undefined, reducedMotion: boolean, fallback: number): number {
  const base = value ?? fallback;
  return reducedMotion ? Math.min(base, 150) : base;
}

function resolveCycleDurationMs(durationSeconds: number | undefined): number {
  if (durationSeconds !== undefined && Number.isFinite(durationSeconds) && durationSeconds > 0) {
    return Math.round(durationSeconds * 1000);
  }
  return PROJECT_WAKE_VIDEO_CYCLE_FALLBACK_MS;
}

export function ProjectWakeTransition({
  projectName,
  visible,
  revealAllLines = false,
  waitingForEditor = false,
  loopAnimation = false,
  fadeInMs,
  fadeOutMs,
  onSkip,
  onHidden,
}: ProjectWakeTransitionProps) {
  const reducedMotion = readReducedMotion();
  const resolvedFadeInMs = clampFadeMs(fadeInMs, reducedMotion, 300);
  const resolvedFadeOutMs = clampFadeMs(fadeOutMs, reducedMotion, 400);
  const showAllLines = revealAllLines || reducedMotion;

  const overlayRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const onHiddenCalledRef = useRef(false);
  const isMountedRef = useRef(true);
  const visibleRef = useRef(visible);
  const waitingForEditorRef = useRef(waitingForEditor);
  const phaseRef = useRef<TransitionPhase>("entering");
  const lineTimerRef = useRef<number | null>(null);
  const startTimeRef = useRef(Date.now());
  const firstCycleCompletedRef = useRef(false);
  const loopRestartInFlightRef = useRef(false);

  const [phase, setPhase] = useState<TransitionPhase>("entering");
  const [visibleLineCount, setVisibleLineCount] = useState(
    showAllLines ? PROJECT_WAKE_TERMINAL_LINES.length : 0
  );
  const [videoHidden, setVideoHidden] = useState(false);
  const [cycleDurationMs, setCycleDurationMs] = useState(PROJECT_WAKE_VIDEO_CYCLE_FALLBACK_MS);
  const [showSlowStartupMessage, setShowSlowStartupMessage] = useState(false);

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  useEffect(() => {
    waitingForEditorRef.current = waitingForEditor;
  }, [waitingForEditor]);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (lineTimerRef.current !== null) {
        window.clearInterval(lineTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      if (isMountedRef.current) {
        setPhase("visible");
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!waitingForEditor) {
      return;
    }
    firstCycleCompletedRef.current = false;
    setShowSlowStartupMessage(false);
    startTimeRef.current = Date.now();
  }, [waitingForEditor]);

  const markSlowStartupIfNeeded = useCallback(() => {
    if (firstCycleCompletedRef.current || !waitingForEditorRef.current) {
      return;
    }
    firstCycleCompletedRef.current = true;
    setShowSlowStartupMessage(true);
  }, []);

  const restartWaitingVideoLoop = useCallback(async () => {
    const video = videoRef.current;
    if (
      !video ||
      loopRestartInFlightRef.current ||
      !waitingForEditorRef.current ||
      !visibleRef.current ||
      phaseRef.current === "fading" ||
      phaseRef.current === "hidden"
    ) {
      return;
    }

    loopRestartInFlightRef.current = true;
    markSlowStartupIfNeeded();
    startTimeRef.current = Date.now();

    try {
      video.currentTime = 0;
      await video.play();
    } catch {
      // Playback can be interrupted when readiness ends the overlay; ignore.
    } finally {
      loopRestartInFlightRef.current = false;
    }
  }, [markSlowStartupIfNeeded]);

  const handleVideoLoadedMetadata = useCallback(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    setCycleDurationMs(resolveCycleDurationMs(video.duration));
  }, []);

  const handleVideoEnded = useCallback(() => {
    if (
      !visibleRef.current ||
      phaseRef.current === "fading" ||
      phaseRef.current === "hidden"
    ) {
      return;
    }

    if (waitingForEditorRef.current) {
      void restartWaitingVideoLoop();
    }
  }, [restartWaitingVideoLoop]);

  useEffect(() => {
    if (lineTimerRef.current !== null) {
      window.clearInterval(lineTimerRef.current);
      lineTimerRef.current = null;
    }

    if (showAllLines && !loopAnimation) {
      setVisibleLineCount(PROJECT_WAKE_TERMINAL_LINES.length);
      return;
    }

    if (loopAnimation) {
      startTimeRef.current = Date.now();
    }

    const updateLines = () => {
      const elapsed = Date.now() - startTimeRef.current;
      const count = loopAnimation
        ? getVisibleTerminalLineCountLooping(elapsed, cycleDurationMs)
        : (() => {
            let visibleCount = 0;
            for (const line of PROJECT_WAKE_TERMINAL_LINES) {
              if (elapsed >= line.delayMs) {
                visibleCount += 1;
              }
            }
            return visibleCount;
          })();
      setVisibleLineCount(count);
    };

    updateLines();
    lineTimerRef.current = window.setInterval(updateLines, 100);
    return () => {
      if (lineTimerRef.current !== null) {
        window.clearInterval(lineTimerRef.current);
        lineTimerRef.current = null;
      }
    };
  }, [showAllLines, loopAnimation, cycleDurationMs]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || videoHidden || reducedMotion) {
      return;
    }
    video.loop = !waitingForEditor;
  }, [waitingForEditor, videoHidden, reducedMotion]);

  useEffect(() => {
    if (!waitingForEditor || (!reducedMotion && !videoHidden)) {
      return;
    }

    const timer = window.setTimeout(() => {
      if (
        waitingForEditorRef.current &&
        visibleRef.current &&
        phaseRef.current !== "fading" &&
        phaseRef.current !== "hidden"
      ) {
        markSlowStartupIfNeeded();
        startTimeRef.current = Date.now();
      }
    }, cycleDurationMs);

    return () => window.clearTimeout(timer);
  }, [
    waitingForEditor,
    reducedMotion,
    videoHidden,
    cycleDurationMs,
    markSlowStartupIfNeeded,
  ]);

  useEffect(() => {
    if (phase !== "hidden") {
      return;
    }
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.pause();
    video.removeAttribute("src");
    video.load();
  }, [phase]);

  useEffect(() => {
    if (visible || phase !== "visible") {
      return;
    }
    setPhase("fading");
  }, [visible, phase]);

  useEffect(() => {
    if (phase !== "fading") {
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
      overlay?.removeEventListener("transitionend", handleTransitionEnd);
      setPhase("hidden");
    };

    const handleTransitionEnd = (event: TransitionEvent) => {
      if (event.target !== overlay || event.propertyName !== "opacity") {
        return;
      }
      finishHide();
    };

    const fallbackTimer = window.setTimeout(finishHide, resolvedFadeOutMs + 100);
    overlay?.addEventListener("transitionend", handleTransitionEnd);

    return () => {
      finished = true;
      window.clearTimeout(fallbackTimer);
      overlay?.removeEventListener("transitionend", handleTransitionEnd);
    };
  }, [phase, resolvedFadeOutMs]);

  useEffect(() => {
    if (phase !== "hidden" || onHiddenCalledRef.current) {
      return;
    }
    onHiddenCalledRef.current = true;
    onHidden();
  }, [phase, onHidden]);

  const handleSkip = useCallback(() => {
    if (phase === "fading") {
      return;
    }
    setVisibleLineCount(PROJECT_WAKE_TERMINAL_LINES.length);
    onSkip();
  }, [onSkip, phase]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || phase === "fading" || phase === "hidden") {
        return;
      }
      event.preventDefault();
      handleSkip();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleSkip, phase]);

  if (phase === "hidden") {
    return null;
  }

  const rootClassName = [
    "wake-transition",
    phase === "fading"
      ? "wake-transition--fading"
      : phase === "visible"
        ? "wake-transition--enter"
        : "",
  ]
    .filter(Boolean)
    .join(" ");

  const style = {
    "--wake-fade-in-ms": `${resolvedFadeInMs}ms`,
    "--wake-fade-out-ms": `${resolvedFadeOutMs}ms`,
  } as CSSProperties;

  const linesToRender = PROJECT_WAKE_TERMINAL_LINES.slice(0, visibleLineCount);

  return (
    <div
      ref={overlayRef}
      className={rootClassName}
      style={style}
      role="status"
      aria-live="polite"
      aria-busy={visible || waitingForEditor}
    >
      <video
        ref={videoRef}
        className={
          videoHidden || reducedMotion
            ? "wake-transition__video wake-transition__video--hidden"
            : "wake-transition__video"
        }
        src={projectWakeIntroVideo}
        autoPlay
        muted
        loop={!waitingForEditor}
        playsInline
        preload="auto"
        aria-hidden="true"
        onLoadedMetadata={handleVideoLoadedMetadata}
        onEnded={handleVideoEnded}
        onError={() => setVideoHidden(true)}
      />
      <div className="wake-transition__projector-anchor">
        <div className="wake-transition__projector-screen">
          <p className="wake-transition__project-title">PROJECT: {projectName}</p>
          <ul className="wake-transition__terminal">
            {linesToRender.map((line) => (
              <li key={line.text} className="wake-transition__terminal-line">
                {line.text}
              </li>
            ))}
          </ul>
          {showSlowStartupMessage ? (
            <p className="wake-transition__slow-startup">{PROJECT_WAKE_SLOW_STARTUP_MESSAGE}</p>
          ) : null}
        </div>
      </div>
      {phase !== "fading" ? (
        <button
          type="button"
          className="wake-transition__skip"
          aria-label="Skip project wake transition"
          onClick={handleSkip}
        >
          Skip
        </button>
      ) : null}
    </div>
  );
}
