# Platform Authoring Library Guide

These modules transform schema, values and package drafts without React, DOM, network, toast or query-cache dependencies.

- Schema `default`/`examples` annotations require the per-node `x-signaldeck-schema: signaldeck.schema/2` opt-in. Preserve explicit marker and annotation presence through codecs; never add annotations to existing definitions. `schema/constraints.ts` preserves and checks supported bounds; server validation remains authoritative. Recursive controls must preserve every legal schema and value shape, including null roots, without JSON/YAML entry or silently discarded constraints.
- `schema/codec.ts` maps the supported JSON Schema subset to schema IR; `values/` encodes/decodes value-entry IR. Preserve optional-field omission, nullable values, discriminated unions and array path rebasing through round trips.
- `parameter-values.ts` preserves scalar, array, object and null parameter roots without wrappers. `schema/launch-input-state.ts` builds object-form drafts and supplies reusable browser shape checks; the backend validates the complete schema for all roots. `schema/schema-template.ts` provides template values. Preserve the difference between omitted, null, empty and defaulted values.
- `common/field-path.ts` owns diagnostic path tokens; reuse them across generated forms and codecs, but map user-facing errors to field labels and editor objects rather than raw paths. Schema title/description are display metadata and must not become runtime fields.
- `common/resource-ref.ts` parses resource identity as `key` or `key@version`; these are not workflow input/output wiring paths. Workflow graph references remain inside the manifest representation. Service/source selectors use these identities internally and show declared names or meaningful generic labels.
- `package-source.ts` reads v2 Workflow Package YAML and applies structural edits with the `yaml` library. Backend source safety, closed schema and graph compilation remain authoritative. Never parse YAML with regex/string splitting or bypass server validation.
- Field rules, mappings, conditions, result sections and budgets are edited through controls against that single source. Preserve untouched fields and values, optional omission, and import/export formats. A generic arbitrary dictionary or source textarea is not a replacement for a supported authoring capability.
- Keep local diagnostic paths deterministic and map backend diagnostics to the correct authoring section. Do not duplicate these transformations in pages or parse YAML with regex/string splitting.

Use the colocated `schema/`, `common/` tests for changed codecs and `src/components/platform-authoring/` tests (relative to `frontend/`) for visible generated-form behavior.
