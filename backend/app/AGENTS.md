# Backend App Guide

[Architecture](../../docs/架构说明.md) owns module responsibilities, dependency direction and the launch, execution, schedule and gateway mechanisms; [development rules](../../docs/开发规范.md#外部合同与凭据) own the external API and credential contracts; [the data model](../../docs/data-model.md) owns tables. This guide routes changes and records invariants the code does not make obvious.

## Routing

- `domain/` and `application/` hold contracts and use cases behind narrow `Protocol` ports, free of HTTP, SQLAlchemy, Temporal, MCP and plugin code; adapters and transactions live in `infrastructure/`, and ORM rows or Sessions never cross a port.
- HTTP: `main.py` owns middleware, error handlers, `/health`, `/ready` and router mounting; `api/platform_router.py` composes `/api`; `api/platform_dependencies.py` composes the launch and persistence adapters. Routes and services raise `ApplicationError` (`domain/execution.py`) with a stable code, and `main.py` maps it and the other handled exceptions to the [error contract](../../docs/开发规范.md#外部合同与凭据).
- Definitions: `domain/definitions.py` (package, Workflow, Agent, node and `Budget` models), `domain/definition_parser.py` (YAML safety, source locations), `domain/compiler.py` (graph semantics, deterministic hashes) and `application/definitions.py` (saves, canonical source). `application/package_import.py` reuses that parser and canonical source, and `PlatformStore.import_package` shares the package identity lock with ordinary saves, so `missing_only` never advances an existing pointer. `infrastructure/package_seeds.py` reads only an explicitly configured directory.
- Launch: `application/task_preparation.py` reuses the `LaunchService` resolution in `application/launch.py` for the review and binding token (`domain/launch_bindings.py`); `infrastructure/platform_run_store.py` stores Run, snapshot and start command in one transaction.
- Processes: `workers/command_dispatcher.py` delivers committed start, cancel and schedule intents; `workers/artifact_worker.py` supervises the retained Core bundles and runs `workers/durable_worker.py` on each bundle's task queue; `workers/schedule_fire.py` keeps a schedule action open until its Run ends.
- Execution: `infrastructure/temporal_workflows.py`, `temporal_agent.py` and `temporal_cancellation.py` own DAG execution, Agent execution and the shared cancellation boundary. `application/execution_projection.py` and `infrastructure/platform_projection_store.py` only record observed terminal facts and never schedule work.
- Tools and models: `application/tool_gateway.py` wraps `infrastructure/mcp_transport.py` and `mcp_cancellation.py`, and model I/O lives in `infrastructure/model_runtime.py`; provider adapters and business persistence belong in `plugins/`, outside the Core import closure.
- Reads: `domain/presentation.py`, `application/result_projection.py` and `infrastructure/run_history.py` own frozen result selectors, result projection and database-wide history paging. History, resource, plugin and schedule reads use stored projections and never resolve credentials, contact plugins or connect to Temporal.
- Persistence: `infrastructure/platform_store.py` owns configuration revisions and runs `create_all` under an advisory lock; `infrastructure/schema_compatibility.py` is the read-only upgrade check ([schema evolution](../../docs/data-model.md#初始化与-schema-演进)).

## Invariants

- `core/encryption.py` rejects a non-empty payload without the `__encrypted__` envelope (plaintext), an unsupported envelope `version`, and a wrong key or invalid token; keep those failures. `infrastructure/secret_storage.py` `EncryptedJSONB` stores the envelopes, and credential values resolve only in I/O adapters from the revision frozen in the binding.
- In `api/platform_packages.py`, literal routes such as `/import` and `/validate-manifest` stay before `/{package_key}`.
- Schedule previews and mutations depend on `get_schedule_service` ([engine availability](../README.md#计划接口)).
- `infrastructure/temporal_agent.py` passes the tool gateway as `DynamicToolset(ToolsetFactory(invoke), id="gateway")` when constructing the `Agent`. With the pinned Pydantic AI 2.40.0, a plain custom `AbstractToolset` is not temporalized and an `@agent.toolset` registration binds too late for durable activities, so keep the wrapper and its stable `id`.

Test routing is in [backend/tests/AGENTS.md](../tests/AGENTS.md); checks are in [CONTRIBUTING](../../CONTRIBUTING.md#检查测试与构建).
