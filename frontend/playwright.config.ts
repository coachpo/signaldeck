import { defineConfig, devices } from "@playwright/test";

const BACKEND_PORT = Number(process.env.SIGNALDECK_E2E_BACKEND_PORT ?? 8001);
const FRONTEND_PORT = Number(process.env.SIGNALDECK_E2E_FRONTEND_PORT ?? 4173);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  timeout: 90_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `node scripts/start-playwright-backend.mjs`,
      port: BACKEND_PORT,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
      timeout: 60_000,
    },
    {
      command: `node scripts/start-playwright-frontend.mjs`,
      port: FRONTEND_PORT,
      reuseExistingServer: false,
      timeout: 15_000,
    },
  ],
});
