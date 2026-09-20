import { createPortal } from "react-dom";
import { grafiHelpTooltipId } from "../../utils/grafiHelpRegistry";
import "./GrafiContextHelpTooltip.css";

const VIEWPORT_MARGIN = 8;
const TOOLTIP_GAP = 8;

export interface GrafiContextHelpTooltipProps {
  topic: string;
  message: string;
  anchorRect: DOMRect;
}

function computePosition(anchorRect: DOMRect): { top: number; left: number } {
  const maxWidth = Math.min(288, window.innerWidth - VIEWPORT_MARGIN * 2);
  let left = anchorRect.right + TOOLTIP_GAP;
  let top = anchorRect.top;

  if (left + maxWidth > window.innerWidth - VIEWPORT_MARGIN) {
    left = anchorRect.left - maxWidth - TOOLTIP_GAP;
  }
  if (left < VIEWPORT_MARGIN) {
    left = Math.max(
      VIEWPORT_MARGIN,
      Math.min(anchorRect.left, window.innerWidth - maxWidth - VIEWPORT_MARGIN)
    );
  }

  const estimatedHeight = 72;
  if (top + estimatedHeight > window.innerHeight - VIEWPORT_MARGIN) {
    top = Math.max(VIEWPORT_MARGIN, anchorRect.bottom - estimatedHeight);
  }
  if (top < VIEWPORT_MARGIN) {
    top = VIEWPORT_MARGIN;
  }

  return { top, left };
}

export function GrafiContextHelpTooltip({
  topic,
  message,
  anchorRect,
}: GrafiContextHelpTooltipProps) {
  const { top, left } = computePosition(anchorRect);

  return createPortal(
    <div
      id={grafiHelpTooltipId(topic)}
      className="grafi-context-help"
      role="tooltip"
      style={{ top: `${top}px`, left: `${left}px` }}
    >
      {message}
    </div>,
    document.body
  );
}
