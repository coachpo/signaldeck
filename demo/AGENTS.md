# Demo Workflow Package Guide

This directory is data only: standalone example Workflow Packages, not platform components or test fixtures ([decoupling principle](../docs/产品说明.md#工作流与平台解耦原则); the examples are described in [README.md](README.md)).

- Tool identities, input/output schemas and resource requirements must match the plugin release descriptors; read [plugins/README.md](../plugins/README.md) and the plugin's `GET /release` descriptor before changing a tool binding.
- Keep credentials, machine-local endpoints and database or run identities out of the packages.
- Follow [the decoupling contract](../docs/工作流解耦方案.md) for `signaldeck.schema/2` defaults and examples and for `signaldeck.presentation/1` input hints, titles and result selectors; task copy and result selectors live in these YAML files.
