# Frontend Guide

Read [`DESIGN.md`](DESIGN.md) for the visual system, tokens and `ui`/`shared` component layering, the [Frontend rules](../docs/开发规范.md#frontend-规则) for drafts, browser storage, retained work and non-secure contexts, and the [product UI contract](../docs/产品说明.md#产品范围) for navigation and interface language. Commands are in [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建); run package scripts from `frontend/`. Narrower guides cover [E2E](e2e/AGENTS.md), the [platform pages](src/pages/platform/AGENTS.md) and the [authoring library](src/lib/platform-authoring/AGENTS.md).

## Change boundaries

- `src/routes.ts` owns browser paths and route handles (breadcrumb, sidebar entry, width and shell mode, state variants); change a handle together with its page. `src/components/layout.tsx` consumes the handles and keeps the plugin host mounted beside the page `Outlet`.
- `src/lib/api-client.ts` owns API base URLs, safe error details and downloads; the clients under `src/lib/api/` call `/api` through `requestPlatform`. `src/lib/user-facing-error.ts` maps errors to recovery guidance; never render API codes, raw details or exception text.
- Hooks own query families: `src/hooks/use-workflow-platform.ts` (definitions, resources, plugins, technical Run and schedule queries), `use-task-experience.ts` (preparation, reuse, task and connection presets), `use-results.ts` (result history, readable results, confirmed reruns) and `use-schedule-preview.ts`; the remaining hooks are named after their data. Keys and invalidation come from `src/lib/query-keys.ts`; keep active polling and launch, rerun and trigger identities through uncertain responses.
- `src/lib/schedule-frequency.ts` and `schedule-calendar.ts` translate schedule controls to and from the existing cron contract and keep untouched parts verbatim; next run times come from the schedule preview API.
- `src/lib/platform-authoring/` owns schema, value and package-source transformations, and `src/components/platform-authoring/` the generated form controls; pages reuse them instead of transforming locally.
- Browser runtime helpers `src/lib/random-uuid.ts`, `clipboard.ts`, `retained-work.ts` and `chunk-recovery.ts` implement the non-secure-context and retained-work parts of the [Frontend rules](../docs/开发规范.md#frontend-规则): call `randomUUID` and `copyText` instead of the browser APIs, and register every new module-level draft or pending-command store with `registerRetainedWork`.
- `src/features/plugin-host/` renders `/apps/:mountKey/*` plugin pages inside the persistent layout; business pages belong to the plugins. `src/plugin-ui/` is built by `pnpm build:plugin-ui` into `plugins/runtime/plugin_runtime/web` and ships inside the Finance and Notes artifacts, so changing it or a shared module it imports changes their artifact digests.

## Validation

- `package.json` is the command source: Vitest for unit and component tests (focused: `pnpm exec vitest run <test-path>`), Playwright for cross-stack flows.
- Keep the React Hooks recommended rules in `eslint.config.js`, including `react-hooks/set-state-in-effect`; fix state synchronization instead of lowering severity.
- Route and layout changes need their component tests and `e2e/shell.spec.ts`.
