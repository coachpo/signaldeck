import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": resolve(import.meta.dirname, "src") } },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: resolve(import.meta.dirname, "../plugins/runtime/plugin_runtime/web"),
    emptyOutDir: true,
    lib: {
      entry: resolve(import.meta.dirname, "src/plugin-ui/index.tsx"),
      name: "SignalDeckUI",
      formats: ["iife"],
      fileName: () => "signaldeck-ui.js",
      cssFileName: "signaldeck-ui",
    },
  },
});
