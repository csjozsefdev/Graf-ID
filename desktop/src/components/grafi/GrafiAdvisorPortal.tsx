import { createPortal } from "react-dom";
import type { ReactNode } from "react";

/** Portals Grafi to `document.body` so `position: fixed` is not clipped by scroll containers. */
export function GrafiAdvisorPortal({ children }: { children: ReactNode }) {
  return createPortal(
    <div className="grafi-advisor-portal" data-grafi-advisor-portal="">
      {children}
    </div>,
    document.body
  );
}
