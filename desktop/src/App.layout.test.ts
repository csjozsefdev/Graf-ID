import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const appCssPath = resolve(dirname(fileURLToPath(import.meta.url)), "App.css");

describe("App layout", () => {
  it("offsets Grafi advisor past the 220px sidebar", () => {
    const css = readFileSync(appCssPath, "utf-8");
    expect(css).toMatch(
      /html\[data-app="graf-id"\]\s*\{[^}]*--grafi-edge-inset-left:\s*calc\(220px\s*\+\s*1rem\)/s
    );
  });

  it("keeps the custom close button fixed above panels and tooltips", () => {
    const css = readFileSync(appCssPath, "utf-8");
    expect(css).toMatch(
      /\.window-close-button\s*\{[^}]*position:\s*fixed;[^}]*z-index:\s*10050;/s
    );
  });
});
