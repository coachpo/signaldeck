# Frontend E2E Guide

Playwright runs Chromium against a disposable PostgreSQL database, fake OpenAI provider, scheduler and built frontend preview.

## Harness

- [`../playwright.config.ts`](../playwright.config.ts) starts owned backend/frontend processes without server reuse. Specs run fully parallel; CI uses one worker and two retries.
- [`../scripts/start-playwright-backend.mjs`](../scripts/start-playwright-backend.mjs) derives PostgreSQL access from `DATABASE_URL` or the backend default, creates a uniquely named `signaldeck_e2e_*` database and drops only that database on shutdown. The database account needs create/drop permission; do not substitute an application database for the owned disposable database.
- Default ports are API `8001`, fake provider `18081`, and frontend `4173`. The provider port/base URL can be overridden by the harness environment.
- [`../scripts/start-playwright-frontend.mjs`](../scripts/start-playwright-frontend.mjs) builds with the E2E API base URL, then starts Vite preview. These are built frontend tests, not a reused dev server.

## Specs

- Seed through Playwright `request` at `http://127.0.0.1:8001/api` or `/api/v1`; keep test data unique because specs run in parallel. Never call real model providers.
- Prefer accessible role/label or stable test-id locators. Wait for specific responses, URLs or polled run states instead of fixed sleeps.
- `workflow-packages.spec.ts` covers authoring, export/import, launch, provider capability blockers and snapshot evidence. `workflow-package-tradingagents-smoke.spec.ts` exercises the ordinary demo fixture with the fake provider.
- `scheduled-tasks.spec.ts` pins `timezoneId: "UTC"` for recurrence assertions and verifies linked runs survive schedule deletion. Normalize timestamps before comparisons.
- `runs.spec.ts` covers monitor/detail and cancellation; `reports.spec.ts` covers template generation, upload, editing and download; `shell.spec.ts` covers navigation and responsive overflow.

Run `pnpm test:e2e` from `frontend/`; select a spec with `pnpm exec playwright test e2e/<file>.spec.ts`. Environment setup and broader checks are in [`CONTRIBUTING.md`](../../CONTRIBUTING.md#检查测试与构建).
