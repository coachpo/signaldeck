# Demo Workflow Package Guide

This directory contains standalone example v2 Workflow Packages, not platform components or test fixtures:

- `research_notes.yaml`: collection-scoped Notes research and a deterministic capture workflow without a model dependency.
- `us_equity_research.yaml`: independently declared equity research and explicit monitoring with Finance and Oracle tools.

Use only the current `signaldeck.workflowPackage/v2` definition root. Keep executable topology in Workflow nodes and business operations in independently deployed plugins. Do not restore private MCP configurations, old SQL presets or compatibility schemas.

Tool identities, input/output schemas and resource requirements must match the independent plugin release descriptors. Read `plugins/README.md` and the corresponding plugin artifact before changing a tool binding. Keep credentials, machine-local endpoints and database/run identities out of the packages.

Platform code, tests, verification scripts, builds and startup configuration must not reference this directory or its contents. Do not generate platform fixtures, locked hashes or other platform artifacts from these examples. Explanatory documentation may link to them. Example changes do not require platform test or implementation changes.

Users may import a selected YAML through the public package import interface. `missing_only` preserves existing keys; explicit updates advance operator revisions. Add `default`/`examples` only on schema nodes explicitly marked `x-signaldeck-schema: signaldeck.schema/2`; use `signaldeck.presentation/1` for input hints, titles and result selectors as defined in [the decoupling contract](../docs/工作流解耦方案.md). Defaults initialize new drafts and must not mutate runtime parameters. Keep task copy and result selectors in these data files, plugin route contracts in independent releases.
