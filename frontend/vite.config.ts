/// <reference types="vitest" />

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frameworkChunkPattern =
  /[/\\]node_modules[/\\](react|react-dom|scheduler|react-router)[/\\]/;
const dataChunkPattern =
  /[/\\]node_modules[/\\]@tanstack[/\\](react-query|react-table)[/\\]/;
const uiChunkPattern =
  /[/\\]node_modules[/\\](@radix-ui|@floating-ui|cmdk|lucide-react|sonner|class-variance-authority|clsx|tailwind-merge)[/\\]/;
const formsChunkPattern = /[/\\]node_modules[/\\](react-hook-form|zod)[/\\]|[/\\]node_modules[/\\]@hookform[/\\]resolvers[/\\]/;
const vendorChunkPattern = /[/\\]node_modules[/\\]/;

// The integrated browser suite uses real owned plugin servers behind one origin.
// Production transport and authorization are verified against Nginx separately.
const integratedProxy = process.env.SIGNALDECK_E2E_INTEGRATED === "1"
  ? Object.fromEntries([
      ["/api", { target: `http://127.0.0.1:${process.env.SIGNALDECK_E2E_BACKEND_PORT ?? "8001"}` }],
      ...JSON.parse(readFileSync(process.env.SIGNALDECK_PLUGIN_MOUNTS_FILE!, "utf8")).mounts.map(
        (mount: { mountKey: string; upstream: string }) => [
          `/_plugins/${mount.mountKey}/`,
          { target: mount.upstream, rewrite: (path: string) => path.slice(`/_plugins/${mount.mountKey}`.length) },
        ],
      ),
    ])
  : undefined;

export default defineConfig({
  preview: { proxy: integratedProxy },
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (frameworkChunkPattern.test(id)) {
            return "framework";
          }

          if (dataChunkPattern.test(id)) {
            return "data";
          }

          if (uiChunkPattern.test(id)) {
            return "ui";
          }

          if (formsChunkPattern.test(id)) {
            return "forms";
          }

          if (vendorChunkPattern.test(id)) {
            return "vendor";
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
