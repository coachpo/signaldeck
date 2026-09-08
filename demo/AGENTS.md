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
uv run black --config pyproject.toml app/infrastructure/package_seeds.py ../demo/sync_seeds.py
uv run pytest tests/test_target_seeds.py tests/test_dag_compiler.py -q
```

`sync_seeds.py` updates the embedded source in `backend/app/infrastructure/package_seeds.py` and `demo/contracts.json`. The startup seed path inserts only missing keys; existing operator revisions must never be overwritten. Add or select runtime and API tests for behavioral changes beyond compilation and seeding. Use the real PostgreSQL fixtures described in `CONTRIBUTING.md`.
