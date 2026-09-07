# Demo Workflow Package Guide

Demo manifests are importable product contracts and the source examples for bundled startup presets:

- [TradingAgents advisory research](tradingagents_advisory_research.yaml) contains finance research workflows and bounded debate loops; its private MCP list is empty.
- [Digital Oracle researcher](digital_oracle_researcher.yaml) contains parallel specialist research, SEC metadata collection, and synthesis, including the package-private Exa `web_research` MCP example.

Keep example changes within the [current product scope](../docs/产品说明.md) and these local constraints:

- Coordinate each demo with its corresponding `backend/app/db/<name>.sql` preset. These seeds embed the YAML, package definition, compiled plan, and extension dependencies; a YAML-only change leaves newly initialized databases with a different example.
- Use stable global Model Connection keys and owner-qualified tools. Keep private MCP credentials as explicit placeholders; never commit real credentials, database/run ids, or machine-local endpoints. Names and descriptions are operator-facing copy.
- Bounded loops are compiled topology. Do not describe the TradingAgents debate-round inputs as dynamically changing the runtime loop bound.
- Do not treat `backend/tests/fixtures/workflow_packages/tradingagents_advisory_research.yaml` as a mirror of the demo: that separate fixture covers private MCP behavior absent from the current TradingAgents demo.
- Check parser/compiler, demo-preset, and execution-plan tests after changing topology or dependencies. Recompute expected manifest/compiled hashes from the compiler; the Digital Oracle API tests also lock hashes. Keep the existing Digital Oracle dependency set unless the compiler contract changes.

From `backend/`, the focused contract checks are:

```bash
uv run pytest tests/test_workflow_package_manifest_parser.py tests/test_workflow_package_manifest_compiler.py tests/test_workflow_package_demo_presets.py tests/test_workflow_package_execution_plan.py
```

For import, preflight, execution, or seed changes, also select the affected cases in `test_workflow_package_api.py`, `test_workflow_package_diagnostics.py`, `test_workflow_package_run_contracts.py`, and `test_db_bootstrap.py`. Use the PostgreSQL test setup in [CONTRIBUTING.md](../CONTRIBUTING.md).
