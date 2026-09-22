# Backend Tests Guide

The database resolution and the Temporal CLI install are in [CONTRIBUTING](../../CONTRIBUTING.md#测试数据库与-e2e-环境), the commands in its [checks section](../../CONTRIBUTING.md#检查测试与构建).

- Database tests use real PostgreSQL, never SQLite.
- Every module that calls `WorkflowEnvironment.start_local` (for example `test_durable_runtime*.py`, `test_target_schedules.py` and `test_execution_tracing.py`) starts a real Temporal dev server from `TEMPORAL_CLI` (default `/tmp/sd-temporal-bin/temporal`, no `PATH` lookup) and fails instead of skipping when it is missing.
- Provider tests use `httpx.MockTransport`, the local protocol servers in `test_durable_runtime_support.py` and `fake_openai_provider.py`, or injected fake yfinance tickers; never depend on real provider credentials or availability.
- Build definitions from `test_dag_compiler.py`, `test_platform_api.py` or `fixtures/`; never read, copy or refer to `demo/`.
- Recovery, cancellation, isolation and unknown write effects need the real Temporal and plugin-process tests; mocked engine or plugin responses do not prove them, so keep those protocol and worker-boundary tests. `test_independent_plugins.py` runs separate plugin processes with their own databases, and the plugin tests (`test_finance_*`, `test_oracle_*`, `test_notes_*`, `test_research_*`) import packages from `plugins/` through `sys.path`.
- Serialize public API models with `model_dump(mode="json", by_alias=True)`, check route presence through `app.openapi()["paths"]` rather than private FastAPI router internals, and assert responses through `TestClient`.
- Test secret absence at read, export and error boundaries; encryption tests may still inspect controlled ciphertext envelopes and wrong-key failures.

## Coverage routing

- Tool recovery: `test_tool_gateway_overlap.py`, `test_tool_gateway_unknown_reconcile.py` and `test_operation_redelivery.py`. Cancellation at evidence boundaries: `test_agent_initial_projection.py`, `test_terminal_projection_cancellation.py`, `test_repeat_workflow_cancellation.py` and `test_mcp_cancellation.py`, next to the durable runtime tests.
- Persistence and projections: `test_platform_persistence.py`, `test_execution_projection.py`, `test_artifact_store_target.py` and `test_schema_compatibility.py`; the explicit cross-run read cache: `test_tool_cache.py`; Finance monitor observations and baselines: `test_research_monitor*.py`. Budgets and usage: `test_execution_budgets.py`, `test_model_budget_contract.py`, `test_model_budget_failures.py`, `test_durable_runtime_budgets.py` and `test_model_usage*.py`.
- `test_task_experience.py` covers preparation and binding consistency, input reuse, database-wide history paging and confirmed result ownership; keep logical unknown effects distinct from recovered network attempts. `test_task_presets.py` covers presets, package-revision revalidation and every JSON input root, including explicit null versus a bookmark; `test_task_drafts.py` covers server drafts.
- Decoupling: `test_presentation_contract.py`, `test_presentation_binding.py`, `test_result_declarations.py` and `test_run_title_declarations.py` keep old hashes stable, renamed fields working, optional skips distinct from declared missing values, confirmed artifact ownership and offline history; concurrent missing-only imports are in `test_platform_api.py::test_missing_only_import_and_operator_save_share_atomic_identity_lock`. Business-looking field names stay ordinary fixture data unless a frozen public declaration selects them.
- Compiler and HTTP API: `test_dag_compiler.py`, `test_core_api.py` and `test_platform_api.py`; anonymous access: `test_public_access.py`.
