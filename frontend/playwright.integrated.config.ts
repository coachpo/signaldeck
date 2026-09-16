import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import base from "./playwright.config";

process.env.SIGNALDECK_E2E_INTEGRATED = "1";
process.env.SIGNALDECK_PLUGIN_MOUNTS_FILE ??= join(tmpdir(), `signaldeck-e2e-mounts-${crypto.randomUUID()}.json`);

export default defineConfig({
  ...base,
  testMatch: ["integrated-plugins.spec.ts", "shell.spec.ts"],
  fullyParallel: false,
  workers: 1,
  webServer: (Array.isArray(base.webServer) ? base.webServer : []).map(server => ({ ...server, timeout: 120_000 })),
});
