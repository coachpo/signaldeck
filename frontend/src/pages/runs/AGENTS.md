# Runs UI Guide

Run pages inspect immutable execution evidence. The browser supports list/detail, cancellation and rerun; backend-only run deletion is not a current UI action.

- `detail.tsx` composes the inspection workspace; `detail-sections/` owns payload and runtime sections. Keep HTTP operation evidence separate from agent invocation evidence.
- `detail-tabs.ts` and `inspection-state.ts` parse tab, target and pane URL state. Preserve deep links to step, agent invocation and HTTP operation evidence, and validate referenced targets against the loaded run.
- Polling lives in `../../hooks/use-runs.ts`: only loaded queued/running runs keep an enabled interval. Use API status/progress fields rather than deriving state from labels.
- `rerun-dialog.tsx` loads the server's frozen-snapshot draft, checks readiness and edits only root parameters. Do not replace its snapshot with the package's current manifest.
- Cancellation feedback must reflect immediate queued cancellation versus cooperative running cancellation. Keep safe error and redaction projections intact when rendering request/response or runtime metadata.

Use `detail-tabs.test.ts`, `detail-http-operations.test.tsx`, `detail-sections.exports.test.ts` and `list.test.tsx` for their corresponding boundaries; hook behavior has tests in `../../hooks/use-runs.test.ts`. Browser inspection and cancellation flows are in `../../../e2e/runs.spec.ts` and `../../../e2e/workflow-packages.spec.ts`.
