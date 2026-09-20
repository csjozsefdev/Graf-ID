import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  GRAFI_SETTINGS_SAVED_EVENT,
  loadGrafiSettings,
} from "../../utils/grafiSettings";
import { grafiHelpTooltipId } from "../../utils/grafiHelpRegistry";

export const GRAFI_HELP_HOVER_DELAY_MS = 400;
export const GRAFI_HELP_LEAVE_DELAY_MS = 150;

interface GrafiHelpContextValue {
  activeHelpTopic: string | null;
  activeHelpRect: DOMRect | null;
  helpingModeEnabled: boolean;
}

const GrafiHelpContext = createContext<GrafiHelpContextValue>({
  activeHelpTopic: null,
  activeHelpRect: null,
  helpingModeEnabled: false,
});

export function useGrafiHelp(): GrafiHelpContextValue {
  return useContext(GrafiHelpContext);
}

function findHelpTopic(element: EventTarget | null): string | null {
  if (!(element instanceof Element)) {
    return null;
  }
  const host = element.closest("[data-grafi-help]");
  return host?.getAttribute("data-grafi-help") ?? null;
}

function findHelpHost(element: EventTarget | null): Element | null {
  if (!(element instanceof Element)) {
    return null;
  }
  return element.closest("[data-grafi-help]");
}

function rectForHost(host: Element | null): DOMRect | null {
  if (!host) {
    return null;
  }
  return host.getBoundingClientRect();
}

function clearDescribedBy(host: Element | null) {
  if (!host) {
    return;
  }
  const describedBy = host.getAttribute("aria-describedby");
  if (describedBy?.startsWith("grafi-help-tooltip-")) {
    host.removeAttribute("aria-describedby");
  }
}

export function GrafiHelpProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(loadGrafiSettings);
  const [activeHelpTopic, setActiveHelpTopic] = useState<string | null>(null);
  const [activeHelpRect, setActiveHelpRect] = useState<DOMRect | null>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const leaveTimerRef = useRef<number | null>(null);
  const activeHostRef = useRef<Element | null>(null);
  const activeTopicRef = useRef<string | null>(null);

  const reloadSettings = useCallback(() => {
    setSettings(loadGrafiSettings());
  }, []);

  useEffect(() => {
    window.addEventListener(GRAFI_SETTINGS_SAVED_EVENT, reloadSettings);
    return () => window.removeEventListener(GRAFI_SETTINGS_SAVED_EVENT, reloadSettings);
  }, [reloadSettings]);

  const helpingModeEnabled = settings.enabled && settings.helpingModeEnabled;

  useEffect(() => {
    if (!helpingModeEnabled) {
      clearDescribedBy(activeHostRef.current);
      setActiveHelpTopic(null);
      setActiveHelpRect(null);
      activeHostRef.current = null;
      activeTopicRef.current = null;
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
      if (leaveTimerRef.current !== null) {
        window.clearTimeout(leaveTimerRef.current);
        leaveTimerRef.current = null;
      }
      return;
    }

    const clearHoverTimer = () => {
      if (hoverTimerRef.current !== null) {
        window.clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
    };

    const clearLeaveTimer = () => {
      if (leaveTimerRef.current !== null) {
        window.clearTimeout(leaveTimerRef.current);
        leaveTimerRef.current = null;
      }
    };

    const activateTopic = (topic: string | null, host: Element | null) => {
      if (activeHostRef.current !== host) {
        clearDescribedBy(activeHostRef.current);
      }
      activeHostRef.current = host;
      activeTopicRef.current = topic;
      setActiveHelpTopic(topic);
      setActiveHelpRect(rectForHost(host));
      if (host && topic) {
        host.setAttribute("aria-describedby", grafiHelpTooltipId(topic));
      }
    };

    const scheduleClear = () => {
      clearLeaveTimer();
      leaveTimerRef.current = window.setTimeout(() => {
        activateTopic(null, null);
      }, GRAFI_HELP_LEAVE_DELAY_MS);
    };

    const scheduleActivate = (topic: string, host: Element) => {
      clearLeaveTimer();
      if (activeHostRef.current === host && activeTopicRef.current === topic) {
        return;
      }
      clearHoverTimer();
      hoverTimerRef.current = window.setTimeout(() => {
        activateTopic(topic, host);
      }, GRAFI_HELP_HOVER_DELAY_MS);
    };

    const onMouseOver = (event: MouseEvent) => {
      const host = findHelpHost(event.target);
      if (!host) {
        return;
      }
      const related = event.relatedTarget;
      if (related instanceof Node && host.contains(related)) {
        return;
      }
      const topic = host.getAttribute("data-grafi-help");
      if (!topic) {
        return;
      }
      scheduleActivate(topic, host);
    };

    const onMouseOut = (event: MouseEvent) => {
      const host = findHelpHost(event.target);
      if (!host || activeHostRef.current !== host) {
        return;
      }
      const related = event.relatedTarget;
      if (related instanceof Node && host.contains(related)) {
        return;
      }
      clearHoverTimer();
      scheduleClear();
    };

    const onFocusIn = (event: FocusEvent) => {
      const topic = findHelpTopic(event.target);
      if (!topic) {
        return;
      }
      clearHoverTimer();
      clearLeaveTimer();
      activateTopic(topic, findHelpHost(event.target));
    };

    const onFocusOut = (event: FocusEvent) => {
      const nextTopic = findHelpTopic(event.relatedTarget);
      if (nextTopic) {
        return;
      }
      clearHoverTimer();
      scheduleClear();
    };

    const updateActiveRect = () => {
      if (activeHostRef.current) {
        setActiveHelpRect(rectForHost(activeHostRef.current));
      }
    };

    document.addEventListener("mouseover", onMouseOver);
    document.addEventListener("mouseout", onMouseOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    window.addEventListener("scroll", updateActiveRect, true);
    window.addEventListener("resize", updateActiveRect);

    return () => {
      clearHoverTimer();
      clearLeaveTimer();
      clearDescribedBy(activeHostRef.current);
      document.removeEventListener("mouseover", onMouseOver);
      document.removeEventListener("mouseout", onMouseOut);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      window.removeEventListener("scroll", updateActiveRect, true);
      window.removeEventListener("resize", updateActiveRect);
    };
  }, [helpingModeEnabled]);

  return (
    <GrafiHelpContext.Provider
      value={{ activeHelpTopic, activeHelpRect, helpingModeEnabled }}
    >
      {children}
    </GrafiHelpContext.Provider>
  );
}
