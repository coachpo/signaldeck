# Scheduled Tasks UI Guide

This subtree owns recurrence authoring, input preview, schedule configuration, fire history and run-now. Follow [`the schedule contract`](../../../../docs/产品说明.md#scheduled-tasks).

- `editor.tsx` creates a schedule for an explicit package/workflow pair. That pair is fixed in update payloads; `detail.tsx` edits timing, inputs and status for the existing target.
- Recurrence is structured (`interval`, `daily`, `weekly`, `monthly`) with an explicit IANA timezone. `pickers.tsx` and `time-zones.ts` supply controls; never substitute the browser timezone for the saved value.
- Input templates may reference `schedule`, `fire`, `window`, `lastRun` and `vars`. Reuse schema-derived defaults and show the preview's rendered parameters and validation errors; preview does not persist or launch.
- Missing/stale manifest or workflow state blocks workflow-dependent input operations and run-now with a reason. Keep independent timing/status management available; do not blanket-disable the entire detail page.
- Preserve overlap (`skip`/`queue`) and misfire (`skip`/`catchUpOne`) choices and their displayed consequences. Run-now sends an idempotency key and scheduled instant, then opens the created ordinary run.
- `../../hooks/use-scheduled-tasks.ts` invalidates schedule list/detail, fire history and linked run scopes after mutations. Preview mutations intentionally do not invalidate caches.
- Deleting a schedule removes its fire history and future automation; existing runs keep run-owned schedule provenance. Confirmation and result text must reflect this distinction.

Authoring payload checks live in `editor.test.tsx`; invalidation checks in `../../hooks/use-scheduled-tasks.test.ts`. `../../../e2e/scheduled-tasks.spec.ts` covers filters, create/preview, pause, run-now and schedule deletion with preserved linked runs; it pins timezone to UTC.
