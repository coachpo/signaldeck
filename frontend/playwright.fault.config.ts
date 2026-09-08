import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import base from "./playwright.config";

// A separate invocation owns the whole stack, so stopping Temporal cannot
// interfere with the ordinary parallel suite or an existing local instance.
process.env.SIGNALDECK_E2E_ALLOW_ENGINE_STOP = "1";
process.env.SIGNALDECK_E2E_CONTROL_FILE ??= join(tmpdir(), `signaldeck-fault-control-${crypto.randomUUID()}.json`);

export default defineConfig({
  ...base,
  testMatch: "faults.spec.ts",
  fullyParallel: false,
  workers: 1,
});
