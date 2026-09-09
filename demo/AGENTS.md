# Demo Workflow Package Guide

Demo YAML is the source contract for bundled v2 Workflow Packages:

- `tradingagents_advisory_research.yaml`: fresh Finance quotes, parallel reusable analyst nodes, explicit risk-review skipping and Finance report persistence.
- `digital_oracle_researcher.yaml`: parallel reusable specialist Agents using independently published Oracle tools, then Finance report persistence.
- `research_notes.yaml`: collection-scoped Notes research and a deterministic capture workflow without a model dependency.

Use only the current `signaldeck.workflowPackage/v2` definition root. Keep executable topology in Workflow nodes and business operations in independently deployed plugins. Do not restore private MCP configurations, old SQL presets or compatibility schemas.

Tool identities, input/output schemas and resource requirements must match the independent plugin release descriptors. Read `plugins/README.md` and the corresponding plugin artifact before changing a tool binding. Keep credentials, machine-local endpoints and database/run identities out of the packages.

After a YAML change, run from `backend/`:

```sh
uv run python ../demo/sync_seeds.py
uv run pytest tests/test_target_seeds.py tests/test_dag_compiler.py tests/test_demo_presentation.py -q
```

`sync_seeds.py` updates only `demo/contracts.json`; it must not generate business YAML into Core Python or app resources. Data is imported through the ordinary parser/canonical revision path. The optional startup directory and `missing_only` API mode atomically preserve existing keys; explicit ordinary updates are required to advance operator revisions. New fields use the closed schema/2 and presentation/1 declarations from [the decoupling contract](../docs/工作流解耦方案.md); defaults are draft annotations, not runtime parameter mutation. Keep task copy and result selectors in these data files, plugin route contracts in independent releases. Add or select runtime and API tests for behavioral changes beyond compilation/import; use real PostgreSQL fixtures from CONTRIBUTING.
