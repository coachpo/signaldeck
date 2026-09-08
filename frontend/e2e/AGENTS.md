# Frontend E2E Guide

Playwright runs Chromium against an owned PostgreSQL database, local fake OpenAI HTTP provider, Temporal dev server, pinned artifact workers, command dispatcher and built frontend preview.

## Harness

- `../playwright.config.ts` starts owned processes without server reuse. Use `pnpm exec playwright test`; specs are independent and can run in parallel.
- `../scripts/start-playwright-backend.mjs` derives PostgreSQL access from `DATABASE_URL` or the backend local default. It creates a unique `signaldeck_e2e_*` database and drops only that database on shutdown. The account requires create/drop permission; never use an application database as disposable test storage.
- Set `TEMPORAL_CLI` to Temporal CLI 1.8.3 with Server 1.31.2. The harness verifies those versions and owns a dev server on port 17233 (`SIGNALDECK_E2E_TEMPORAL_PORT` override). It does not attach to an existing Temporal server.
- Every invocation creates an owned temporary directory for Temporal data, CAS artifacts, immutable core bundles and Python environments. Shutdown waits for owned process groups, unlocks only directories under that owned path without following symlinks, then removes it. Do not delete any shared application volumes or core bundles.
- Default ports are API 8001, fake provider 18081, Notes 18082, Finance 18083, Oracle 18084 and frontend 4173. Independent plugins use separately owned databases; Finance injects a deterministic quote provider and Oracle injects a controlled sentiment HTTP client. Deployment connection presets are written only under the owned temporary directory. The provider port/base URL are overridable. The pinned worker uses Python 3.13.13; the locked local API interpreter is resolved through uv.
- `../scripts/start-playwright-frontend.mjs` builds with the E2E API base URL and starts Vite preview. Browser validation targets the production build. Logfire credentials/configuration and OTLP exporter endpoints are isolated so the local harness does not send telemetry to external services.

## Coverage

- `platform-fixtures.ts` uses v2 Package definitions and explicit global resource bindings. Disable YAML aliases when serializing reused schema objects; backend source safety remains authoritative.
- `workflow-packages.spec.ts` covers shared YAML/structure edits, merged edge sources, cycle diagnostic locations, applied launch inputs, browser closure during execution, invocation evidence, frozen snapshots and rerun identity.
- `parameters.spec.ts` verifies array inputs pass unchanged through the same definition for manual and scheduled launches, including an empty array and immutable Run inspection.
- `faults.spec.ts` owns a separate held MCP process and verifies actual unknown write effects after cancellation, guarded replay and historical reads after plugin shutdown. Run `pnpm exec playwright test --config playwright.fault.config.ts` as a separate invocation to also stop only its harness-owned Temporal process and verify persisted history with both dependencies offline. The isolated configuration submits a nonce-bound file request to the harness; it does not signal discovered processes or expose product control routes.
- `runs.spec.ts` coordinates a held local HTTP request, then verifies running cancellation reaches actual stopped state without fabricating model output.
- `resources.spec.ts` verifies write-only credentials through save, read and reload.
- `scheduled-tasks.spec.ts` verifies explicit timezone/overlap/missed-fire window, synchronization status, trigger acceptance, independent Run provenance, failure history and retained runs after schedule deletion. It pins browser timezone to UTC.
- `tasks.spec.ts` exercises the four ordinary task forms with actual MCP plugin processes, durable execution, controlled model/market data, missing-model inline repair, uncertain-response retry, input reuse and immutable run/result evidence. Each scenario captures filled forms, ready-to-start settings and executed results at 375, 768, 1024 and 1440 pixels; trial clicks and viewport bounds verify key actions remain reachable. Evidence is saved under `output/playwright/task-experience/`. These are automated observations, not participant or external supplier acceptance.
- `shell.spec.ts` covers generic navigation without statically compiled plugin pages and responsive overflow at 375, 768, 1024 and 1440 pixels. It captures editor screenshots for visual inspection.

Use accessible role/label locators and explicit response/state waits. Never call a real model provider or use arbitrary sleeps to make a failing assertion pass. Tests prove only the behaviors actually exercised; component tests and backend acceptance cover additional cancellation, failure and recovery boundaries.
