# Backend App Guide

These boundaries describe the current SD-TARGET-001 implementation. Use the frozen target referenced by [STATUS.md](../../STATUS.md#冻结迭代目标) for acceptance; current source structure alone does not prove completion.

## Change Boundaries

- `domain/` owns definition, graph, schema, resource and tool contracts; `application/` owns use cases and narrow ports. Keep HTTP, SQLAlchemy, Temporal, MCP and plugin business implementation out of those contracts. Concrete adapters and transaction ownership belong in `infrastructure/`; do not pass ORM rows or Sessions through application ports.
- `main.py` owns middleware, errors, health and router mounting; `api/platform_dependencies.py` composes launch and persistence adapters. `workers/command_dispatcher.py` delivers committed commands and schedule updates; `workers/artifact_worker.py` supervises immutable core bundles and launches `workers/durable_worker.py` on the matching artifact queue.
- `infrastructure/temporal_workflows.py` and `temporal_agent.py` own durable DAG and Agent execution. Keep confirmed model/tool results, independent node progress, cancellation and the original deadline recoverable through the engine; query projection in `application/execution_projection.py` only observes terminal facts.
- `infrastructure/platform_store.py` initializes PostgreSQL under an advisory lock. `create_all` does not alter existing tables; `infrastructure/package_seeds.py` inserts only missing package keys. Preserve atomic Run/snapshot/start-command persistence and immutable revision conflicts in the store adapters. Model changes must agree with [the data model](../../docs/data-model.md).
- `core/encryption.py` owns credential envelopes; `infrastructure/secret_storage.py` supplies `EncryptedJSONB`. Preserve failure on wrong keys, non-empty plaintext payloads and unsupported envelope versions. Keep credential revisions in bindings and resolve values only in I/O adapters.
- `application/tool_gateway.py` enforces the frozen catalog, grants, schema, operation identity and result evidence before/after `infrastructure/mcp_transport.py` calls independent plugins. Provider business adapters and Finance persistence belong in the repository's `plugins/` directory, outside the core import closure.

## Read and Validation Boundaries

- `schemas/common.py` provides `CamelModel`; use `core/errors.py` for service/API errors and browser-safe details. Token middleware's 401 response is a separate existing contract.
- Historical package/run, resource, plugin and schedule reads use stored safe projections. Do not resolve credentials, contact plugins or connect to Temporal merely to display history. Artifact downloads verify content-addressed references through their dedicated adapter.
- Read [architecture](../../docs/架构说明.md) for current dependencies, [development rules](../../docs/开发规范.md) for backend contracts, and [CONTRIBUTING](../../CONTRIBUTING.md) for checks. API and backend tests have narrower guides.
