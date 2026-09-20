import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const packageJson = JSON.parse(
  readFileSync(fileURLToPath(new URL("./package.json", import.meta.url)), "utf-8")
) as { version: string };

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version),
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["src/test/setup.ts"],
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    headers: {
      "Cache-Control": "no-store",
    },
    // Vite must not watch Rust build output (Windows EBUSY on locked .exe files).
    watch: {
      ignored: [
        "**/src-tauri/target/**",
        "**/src-tauri/runtime/**",
        "**/src-tauri/gen/**",
      ],
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2020",
    minify: !process.env.TAURI_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});
