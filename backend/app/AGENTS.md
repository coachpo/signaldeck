# Backend App Guide

## Change Boundaries

- Keep HTTP adapters in `api/`, public contracts in `schemas/`, orchestration and transaction ownership in `services/`, and query/persistence operations in `repositories/`. Provider adapters also live in `services/`; follow the existing interface instead of assuming all external I/O belongs in extensions.
- Use `main.py` for middleware, error handlers, health checks and router mounting; use `api/dependencies.py` for request-scoped service wiring and `workers/run_scheduler.py` for worker composition.
- `db/session.py` owns PostgreSQL initialization under an advisory lock. `create_all` does not alter existing tables; preset SQL upserts can overwrite same-key package definitions at startup.
- Model and cascade changes must agree with [the data model](../../docs/data-model.md). `models/run.py` requires a run-owned executable snapshot before flushing a Workflow Package run.
- `models/base.py` owns `EncryptedJSONB`. Preserve failure on wrong keys, non-empty plaintext payloads and unsupported envelope versions; ordinary JSONB columns are not implicitly encrypted.
- Keep runtime execution in `agents/`, `services/` and static `extensions/`; there is no separate `app/runtime` package.

## Read and Validation Boundaries

- `schemas/common.py` provides `CamelModel`; use `core/errors.py` for service/API errors and browser-safe details. Token middleware's 401 response is a separate existing contract.
- Historical package/run reads use explicit safe projections. Runtime Model Connection keys and package bindings must not be resolved merely to display history.
- Read [architecture](../../docs/架构说明.md) for current dependencies, [development rules](../../docs/开发规范.md) for backend contracts, and [CONTRIBUTING](../../CONTRIBUTING.md) for checks. API, services, extensions and tests have narrower guides.
