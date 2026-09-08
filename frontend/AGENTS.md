# Frontend Guide

Read [`DESIGN.md`](DESIGN.md) for the visual system and [`Frontend rules`](../docs/开发规范.md#frontend-规则) for implementation constraints. Validation commands are maintained in [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建); run them from `frontend/` when using package scripts directly.

## Change boundaries

- `src/routes.ts` owns browser paths and route handles: sidebar ownership, breadcrumbs, width, scroll/full-height mode, and state variants. Change route metadata together with its page; `src/components/layout.tsx` consumes those handles.
- `src/styles/theme.css` owns semantic tokens. `src/components/ui` holds primitives; `src/components/shared` holds management shells and reusable presentational controls. Keep route parameters, API state, domain copy, validation and navigation with the owning feature.
- `src/lib/api-client.ts` owns API base URL normalization, token retry, safe error details and downloads. `src/lib/api/workflow-platform.ts` uses `requestPlatform` for `/api` platform endpoints. Independent plugins own their business pages.
- `src/hooks/use-workflow-platform.ts` owns TanStack Query calls, active Run/schedule polling and invalidation using `src/lib/query-keys.ts`. Keep launch/rerun/trigger identities stable through uncertain responses and invalidate the affected Run and schedule scopes after commands.
- Normal navigation is tasks/results/settings; expert mode changes presentation only. `src/hooks/use-display-mode.ts` persists display preferences, never task inputs or credentials. Keep mode switches free of navigation or command side effects; preserve mounted draft editors and advanced values.
- `src/pages/platform/task-catalog.ts` maps the first business scenarios to existing package/workflow keys. Use the actual schema and retain the expert fallback when a dedicated form cannot represent all fields; this catalog must not become an execution definition. `use-task-experience.ts` and `use-results.ts` own their API queries through `queryKeys`.
- `src/lib/schedule-frequency.ts` translates common controls to the existing cron contract. Preserve unsupported cron and saved timezone; use the Temporal preview API for next execution times, distinguishing desired and synced revisions.
- `src/lib/platform-authoring/` owns schema/value codecs; generated form components live in `src/components/platform-authoring/`. Keep transformations out of page components when these helpers already provide them.

## Validation

- `package.json` is the command source; unit/component tests use Vitest, cross-stack flows use Playwright. Run focused tests with `pnpm exec vitest run <test-path>` before broader checks when implementation changes warrant them.
- Preserve `eslint.config.js`'s React Hooks recommended rules, including `react-hooks/set-state-in-effect`; fix state synchronization rather than lowering severity.
- Route and layout changes need the corresponding component tests and `e2e/shell.spec.ts` coverage. `src/pages/platform/AGENTS.md` and schema/value guides own the corresponding behavior boundaries.
