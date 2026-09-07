# Workflow Packages UI Guide

This subtree owns package list/import/edit/export, Secret Bindings and the dedicated launch page. Follow [`the product contract`](../../../../docs/产品说明.md#工作流包与启动).

- `editor.tsx` must hydrate resource drafts from `manifestSource`, not package summary metadata. Failed manifest reads or parsing block authoring; preserve retry and dirty-draft protection.
- Editing and launching are separate routes. A launch uses the persisted package; dirty editor handoff must acknowledge that unsaved changes are excluded. Preserve the separate Open and Launch actions in `list.tsx`.
- `editor-sections.tsx` owns package-local resource sections; workflows, including HTTP nodes, remain structured data edited through Workflow YAML. Reuse `../../lib/platform-authoring/workflow-packages/manifest.ts` for draft conversion and diagnostic routing.
- `launch.tsx` requires an explicitly selected workflow from the current manifest. Reset inputs when the workflow/schema changes and readiness when workflow selection changes; stale selections must not launch.
- Schema-backed form mode and advanced JSON share one validated payload. Apply JSON back through the launch-input codec before preflight/launch; keep the JSON fallback for schemas unsupported by generated forms. Launch rechecks preflight for the current inputs.
- Secret Binding values are write-only and cleared after saving. Operators may enter new private MCP `env`, `headers` and `query` values in the editor; persisted values must not be reconstructed from reads or echoed in export/provenance.
- Diagnostic focus must resolve to the current field after tab changes without trapping users who have moved to another field.

Validate relevant editor/import/HTTP/secret-binding behavior with colocated tests. Full launch, schema-input and snapshot flows are covered by `../../../e2e/workflow-packages.spec.ts`.
