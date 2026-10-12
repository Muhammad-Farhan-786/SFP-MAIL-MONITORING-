import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { existsSync } from "node:fs";
export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_LOGO_AVAILABLE": JSON.stringify(
      existsSync(
        new URL("./public/branding/newhotmusic-logo.png", import.meta.url),
      ),
    ),
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks: (id: string) =>
          id.includes("recharts") || id.includes("d3-")
            ? "charts"
            : id.includes("/react/") || id.includes("/react-dom/")
              ? "react"
              : undefined,
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: {
    exclude: ["e2e/**", "node_modules/**"],
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
