# Frontend Guide

Read [`DESIGN.md`](DESIGN.md) for the visual system and [`Frontend rules`](../docs/开发规范.md#frontend-规则) for implementation constraints. Validation commands are maintained in [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建); run them from `frontend/` when using package scripts directly.

## Change boundaries

- `src/routes.ts` owns browser paths and route handles: sidebar ownership, breadcrumbs, width, scroll/full-height mode, and state variants. Change route metadata together with its page; `src/components/layout.tsx` consumes those handles.
- `src/styles/theme.css` owns semantic tokens. `src/components/ui` holds primitives; `src/components/shared` holds management shells and reusable presentational controls. Keep route parameters, API state, domain copy, validation and navigation with the owning feature.
- `src/lib/api-client.ts` owns API base URL normalization, token retry, safe error details and downloads. `src/lib/api/` selects `request` for `/api/v1` extension endpoints or `requestPlatform` for `/api` platform endpoints.
- `src/hooks/` owns TanStack Query calls and invalidation using `src/lib/query-keys.ts`. Batch delete hooks settle all requests and invalidate affected scopes even on partial failure; preserve that behavior.
- `src/lib/platform-authoring/` owns schema/value codecs; generated form components live in `src/components/platform-authoring/`. Keep transformations out of page components when these helpers already provide them.

## Validation

- `package.json` is the command source; unit/component tests use Vitest, cross-stack flows use Playwright. Run focused tests with `pnpm exec vitest run <test-path>` before broader checks when implementation changes warrant them.
- Preserve `eslint.config.js`'s React Hooks recommended rules, including `react-hooks/set-state-in-effect`; fix state synchronization rather than lowering severity.
- Route and layout changes need the corresponding component tests and `e2e/shell.spec.ts` coverage. Package, schedule, run and schema/value subtrees have narrower guides for their behavior boundaries.
