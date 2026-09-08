# Independent business plugins

These services are separately built Python artifacts. No service imports the Core `app` package or reads Core tables. `runtime/plugin_runtime` is a small, source-distributed MCP transport, wire projection and operation journal library. Each image includes its own fixed copy; installing a new plugin does not register Python business code in Core or Worker.

| Artifact | Business ownership | MCP endpoint | Additional surface |
| --- | --- | --- | --- |
| `finance` | Templates, Reports, market quotes/history/OHLCV/indicators/fundamentals/news/social sentiment/insider data | `/mcp/` | Finance page `/`; own `/api/templates` and `/api/reports` |
| `digital_oracle` | Prediction markets, SEC filings, market sentiment, macro rates, crypto derivatives, CFTC positioning and options providers | `/mcp/` | Stateless provider service |
| `notes` | Non-financial immutable notes and collection search | `/mcp/` | Own PostgreSQL business records |

Finance provider implementations and template/report compiler were extracted from the former Finance extension. Digital Oracle retains its existing bounded provider clients, normalization and source warnings in the Oracle artifact. These are business modules, not a copy of Core. The former host context, host registry and host database ownership are absent. Finance does not silently serve a previous Run's cached quote when a fresh provider lookup fails. Unavailable optional Oracle providers report their absence; no synthetic upstream evidence is generated.

## Build and run

Build context is this `plugins` directory, not the individual project directory:

```sh
docker build -f finance/Dockerfile -t signaldeck-finance:1.0.0 .
docker build -f digital_oracle/Dockerfile -t signaldeck-digital-oracle:1.0.0 .
docker build -f notes/Dockerfile -t signaldeck-notes:1.0.0 .
```

Each image pins Python 3.14.0 and uv 0.9.8 by image digest and contains an independently frozen `uv.lock`. Direct application dependencies include MCP 1.26.0, FastAPI 0.136.3, Pydantic 2.12.5, SQLAlchemy 2.0.51, psycopg 3.3.4 and JSON Schema 4.26.0. MCP protocol is **2025-11-25**.

Finance and Notes require `PLUGIN_DATABASE_URL`, pointing to a separately owned PostgreSQL database/role. Neither falls back to Core's `DATABASE_URL`. Startup creates only that plugin's business tables and operation journal. Finance owns `reports`, `text_templates` and `market_quotes`; Notes owns `notes`; each owns its own `plugin_operations`. Oracle has no business persistence requirement. Existing Core business data is **not** migrated, reset or read by these services.

For a local Python process, run `uv sync --frozen` in the chosen project. Set `PYTHONPATH` to that project directory plus `plugins/runtime`, then use one of:

```sh
uv run uvicorn finance_plugin.main:create_app --factory --host 127.0.0.1 --port 8091 --no-access-log
uv run uvicorn oracle_plugin.main:app --host 127.0.0.1 --port 8092 --no-access-log
uv run uvicorn notes_plugin.main:create_app --factory --host 127.0.0.1 --port 8093 --no-access-log
```

Set `PLUGIN_ENDPOINT` to the exact reachable MCP URL including `/mcp/`. Finance's `PLUGIN_PAGE_URL` points to its independently served page, defaulting to `http://localhost:8091/`. `GET /release` supplies the complete installation descriptor; `GET /health` reports the running release. Install descriptors through Core's generic plugin catalog. A disabled or unavailable plugin does not need to be imported for Core history reads.

Oracle resolves its own optional `FRED_API_KEY` and `EDGAR_CONTACT_EMAIL` from the plugin's deployment environment, at its own I/O boundary. They are never returned in descriptors, MCP metadata or model messages. Scope references and grants carry no credentials. Production provider access was not exercised by local tests.

## Frozen contracts and resource scopes

Tool IDs are qualified by owner: for example `signaldeck/finance/reports_create`, `signaldeck/digital-oracle/market_sentiment_lookup` and `example/notes/create`.

The descriptor's tool definitions are the sole source of `tools/list`, dispatch lookup, input validation and output validation. Schemas are a closed 2020-12 subset with explicit `unevaluatedProperties: false`. The wire representation omits nullable optional fields, represents decimal values as strings, and projects warning detail maps as key/value arrays. Date fields are ISO strings; typed provider projections validate dates before serialization. This wire contract replaces the previous nullable OpenAI argument declarations and host DTO representation.

| Tool | Arguments | Required resource and non-sensitive scope |
| --- | --- | --- |
| `example/notes/create` | `title`, `text` | `notes-workspace`: `{"collection":"research"}` |
| `example/notes/search` | Optional `query`, `limit` | `notes-workspace`: `{"collection":"research"}` |
| `signaldeck/finance/market_data_quote_lookup` | `symbols` | `finance-market-data`: `{"allowedSymbols":["MSFT","AAPL"]}` |
| Other Finance market tools | See published contract | `finance-market-data`: `allowedSymbols` limits symbol arguments |
| `signaldeck/finance/reports_create` | `name`, `content` | No resource required; persists immutable Agent provenance from the call identity |

The Gateway sends only the granted resource scopes in `_meta["signaldeck/context"].resourceBindings`. Notes stores and filters the collection in business SQL; Finance rejects symbols outside its scope. Missing required grants are rejected at the MCP boundary. Report reads and the Finance business page are owned by Finance, not the Core API.

## Operations and upgrades

Each business invocation carries the exact four-field release identity in `_meta["signaldeck/release"]`: `pluginId`, `releaseId`, `artifactDigest`, `contractDigest`. A process rejects a different binding. `VERSION`, distributed code, web assets, Dockerfile and lockfile bytes determine artifact identity; Oracle additionally binds its resolved non-sensitive deployment settings to that identity; the contract digest independently covers all advertised tool definitions.

Release upgrades use a **new immutable artifact and endpoint**. Retain the old image/process and old endpoint while frozen Runs still reference them. Changing a running endpoint to a new release causes old requests to fail explicitly; it does not substitute new code. The independent upgrade test runs Notes 1.0.0 and 1.1.0 simultaneously, confirms distinct artifact identity, rejects a mismatched binding, and continues calls to the original release.

Notes writes and Finance Agent-report writes use a PostgreSQL transaction for the business effect and immutable operation result. An operation-scoped advisory lock prevents concurrent duplication. Reuse of an operation ID with different arguments, tool or scope is rejected. `signaldeck/operations/query` returns `unknown` while the effect transaction holds the lock, `succeeded` plus the saved result after commit, or authoritative `not_found` after rollback/absence. It also checks the stored tool grant and resource scope before exposing a result. This deduplication covers these database writes, not arbitrary remote-provider side effects.

Agent-created Finance reports cannot be overwritten or deleted through the business API. The Notes service creates immutable records; subsequent work creates a new operation/record.

## Local validation

From `backend`:

```sh
uv run pytest tests/test_independent_plugins.py -q
```

After building all three images with tags `signaldeck-finance:sd-target-001`, `signaldeck-digital-oracle:sd-target-001` and `signaldeck-notes:sd-target-001`, run the locked-image check from the repository root:

```sh
backend/.venv/bin/python plugins/tests/image_smoke.py
```

This provisions UUID-named local test databases, starts only the three named test containers, verifies Finance HTTP compilation plus MCP report writes/query and Notes MCP writes/query, then removes those containers and databases in `finally` cleanup.

The tests use actual isolated PostgreSQL databases and a real MCP Streamable HTTP client/server. They cover independent imports, published closed schemas, Finance CRUD/compile/upload/download and provenance protection, money strings and fresh-read behavior, operation dedupe/conflict/in-flight query/rollback, resource isolation, simultaneous old/new Notes releases, protocol/grant/schema rejection, private-role denial of Core-table access, and an Oracle provider projection using a controlled HTTP fixture. No model service or paid market provider is called. Full Core/Worker/Compose acceptance is a separate integration boundary; these tests alone do not prove the platform contracts in [the product acceptance criteria](../docs/产品说明.md#验收标准).
