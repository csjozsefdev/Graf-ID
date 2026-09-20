import { createPortal } from "react-dom";

import { requestMainWindowClose } from "../utils/mainWindowClose";

export function WindowCloseButton() {
  return createPortal(
    <button
      type="button"
      className="window-close-button"
      aria-label="Close Graf-ID"
      onClick={() => {
        void requestMainWindowClose();
      }}
    >
      <svg
        className="window-close-button__icon"
        viewBox="0 0 12 12"
        width="12"
        height="12"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M1.05 1.05 10.95 10.95M10.95 1.05 1.05 10.95" />
      </svg>
    </button>,
    document.body
  );
}
