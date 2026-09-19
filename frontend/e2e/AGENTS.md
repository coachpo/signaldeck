# Frontend E2E Guide

Every Playwright invocation starts its own stack through `../scripts/start-playwright-backend.mjs` and `start-playwright-frontend.mjs`; the launcher builds the shared plugin UI first and gives Finance and Oracle controlled market and sentiment data. The services, ports, overrides, database access and build-directory rules are in [CONTRIBUTING](../../CONTRIBUTING.md#测试数据库与-e2e-环境).

## Running

Commands and when to run each configuration are in [CONTRIBUTING](../../CONTRIBUTING.md#检查测试与构建).

- `playwright.config.ts` (`pnpm test:e2e`) runs the specs in parallel, skips `integrated-plugins.spec.ts` and runs `faults.spec.ts` without stopping Temporal; under `CI` it uses one worker and two retries.
- `playwright.integrated.config.ts` runs `integrated-plugins.spec.ts` and `shell.spec.ts` with one worker and writes its mount registry to `<os tmpdir>/signaldeck-e2e-mounts-<uuid>.json` unless `SIGNALDECK_PLUGIN_MOUNTS_FILE` is set.
- `playwright.fault.config.ts` stops Temporal only through a nonce-bound request file to the launcher; it never signals discovered processes or exposes product control routes.

## Safety

- The launcher creates and drops only `signaldeck_e2e_*` databases and refuses other names; never point it at an application database as disposable storage.
- Shutdown removes only what the launcher created: its temporary directory (without following symlinks) and the fault-control and mount-registry files it wrote. Never delete shared application volumes or Core bundles.
- Never call a real model provider or use arbitrary sleeps to make an assertion pass.

## Writing specs

- One Core database serves every spec and every retry of an invocation, and resources cannot be deleted through the API, so a test must tolerate what earlier specs or attempts saved (see the `reused-connection` annotation in `tasks.spec.ts`).
- Build fixtures with `platform-fixtures.ts`, `task-fixtures.ts` and `task-package-fixtures.ts`: independent v2 definitions with explicit resource bindings. Never read or refer to `demo/`. Serialize reused schema objects with `aliasDuplicateObjects: false`.
- Use accessible role and label locators and explicit response or state waits.
- Prove scroll reachability with `page.mouse.wheel` or keyboard scrolling plus `toBeInViewport()`, as `result-reading.spec.ts` does; `click({ trial: true })` also passes on content clipped by `overflow: hidden`.
- `pnpm typecheck` does not cover `e2e/`; ESLint does, so run `pnpm lint` after editing specs.

## Spec ownership

| Spec | Owns |
| --- | --- |
| `tasks.spec.ts` | Four ordinary tasks with real plugins: inline connection repair, uncertain-launch retry with the same `launchId`, readable results, Markdown download, input reuse and four-width evidence. |
| `history.spec.ts` | Server-side history filters and pagination snapshots across result and evidence navigation and refresh, with local-date boundaries in a non-UTC browser timezone. |
| `result-reading.spec.ts` | Long results read by wheel and keyboard, with reachable evidence actions, at five viewports. |
| `runs.spec.ts` | Running cancellation reaching an actual stopped state without fabricated output. |
| `faults.spec.ts` | Unknown write effects after cancellation, the guarded rerun, and results, history, export and updates after plugin shutdown (and Temporal shutdown under the fault config). |
| `scheduled-tasks.spec.ts` | Timezone, overlap and missed-trigger window, synchronization state, trigger provenance, failed launches, runs retained after deletion, and weekly and custom schedules across modes (browser pinned to UTC). |
| `parameters.spec.ts` | Through ordinary controls, an array input root for manual and scheduled launches and an exact null root for a manual launch. |
| `decoupling.spec.ts` | Public batch import, schema/2 defaults, renamed and business-looking fields, frozen declared results and concurrent missing-only imports (D01–D04, D06). |
| `workflow-packages.spec.ts` | Imported workflows edited through named controls and the graph, cycle diagnostics at the affected control, and durable results after the browser closes. |
| `expert.spec.ts` | Expert authoring with named controls, drafts across mode switches and navigation, graph zoom and layout, file import and export, and diagnostic navigation at four widths. |
| `expert-resources.spec.ts` | Service and plugin-installation drafts surviving mode switches without write requests or credentials in browser storage. |
| `resources.spec.ts` | Write-only credentials through save and reload. |
| `model-usage.spec.ts` | Output-budget editing, readable model usage, and task budgets surviving server-draft restore and freezing per run. |
| `shell.spec.ts` | Generic navigation without statically compiled plugin pages; creation, edit and detail pages with `crypto.randomUUID`, `crypto.subtle` and `navigator.clipboard` deleted by an init script, as on a plain-HTTP LAN address, where the copied result must equal the exported Markdown; one reload after a failed lazy chunk; and responsive overflow at four widths. |
| `integrated-plugins.spec.ts` | Plugin pages in the unified host: drafts across plugin navigation, Finance deep links and four widths, a confirmed Notes result opening its workspace and copying over plain HTTP, generic-plugin deep links, and disabled or absent mounts. |

## Browser review

For a browser experience review, define the user goal and the success condition first, then find controls only from visible UI. Fixture APIs may prepare isolated data and code or API inspection may diagnose failures, but neither may complete the user's steps. Cover the normal and the recovery path of each affected change and keep before and after screenshots; automated tests do not replace this review.
