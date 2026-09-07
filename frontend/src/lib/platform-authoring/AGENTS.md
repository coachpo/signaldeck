# Platform Authoring Library Guide

These modules transform schema, values and package drafts without React, DOM, network, toast or query-cache dependencies.

- `schema/codec.ts` maps the supported JSON Schema subset to schema IR; `values/` encodes/decodes value-entry IR. Preserve optional-field omission, nullable values, discriminated unions and array path rebasing through round trips.
- `schema/launch-input-state.ts` builds launch drafts, validates advanced JSON and exposes unsupported-schema fallback. `schema/schema-template.ts` provides template values. Preserve the difference between omitted, null, empty and defaulted values.
- `common/field-path.ts` owns diagnostic path tokens; reuse them across generated forms and codecs. Schema title/description are display metadata and must not become runtime fields.
- `common/resource-ref.ts` parses resource identity as `key` or `key@version`; these are not workflow input/output wiring paths. Workflow graph references remain inside the manifest representation.
- `workflow-packages/manifest.ts` converts package drafts and Workflow YAML using the `yaml` library. Its client-side checks help authoring; the backend parser remains authoritative for source safety, closed fields and graph semantics. Never treat successful frontend parsing as permission to bypass backend validation.
- Keep local diagnostic paths deterministic and map backend diagnostics to the correct authoring section. Do not duplicate these transformations in pages or parse YAML with regex/string splitting.

Use the colocated `schema/`, `common/` and `workflow-packages/` tests for changed codecs and `src/components/platform-authoring/` tests (relative to `frontend/`) for visible generated-form behavior.
