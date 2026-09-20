import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

let matchMediaMatches = false;

export function setMatchMediaMatches(matches: boolean) {
  matchMediaMatches = matches;
}

afterEach(() => {
  cleanup();
  matchMediaMatches = false;
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: matchMediaMatches,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: (_event: string, handler: (event: MediaQueryListEvent) => void) => {
      handler({ matches: matchMediaMatches, media: query } as MediaQueryListEvent);
    },
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
