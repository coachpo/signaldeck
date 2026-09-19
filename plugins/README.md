# Independent business plugins

These services are separately built Python artifacts. No service imports the Core `app` package or reads Core tables. `runtime/plugin_runtime` is a small, source-distributed MCP transport, wire projection and operation journal library. Each image includes its own fixed copy; installing a new plugin does not register Python business code in Core or Worker.

| Artifact | Business ownership | MCP endpoint | Additional surface |
| --- | --- | --- | --- |
| `finance` | Templates, Reports, market quotes/history/OHLCV/indicators/K-line events/fundamentals/news/social sentiment/insider data | `/mcp/` | [Report workspace](finance/README.md) at `/`; own `/api/templates` and `/api/reports` |
| `digital_oracle` | Prediction markets, SEC filings, market sentiment, macro rates, crypto derivatives, CFTC positioning and options providers | `/mcp/` | Stateless provider service |
| `notes` | Non-financial immutable notes and collection search | `/mcp/` | Own PostgreSQL business records |

Finance provider implementations and template/report compiler were extracted from the former Finance extension. Digital Oracle retains its existing bounded provider clients, normalization and source warnings in the Oracle artifact. These are business modules, not a copy of Core. The former host context, host registry and host database ownership are absent. Finance does not silently serve a previous Run's cached quote when a fresh provider lookup fails. Unavailable optional Oracle providers report their absence; no synthetic upstream evidence is generated.

## Build and run

Run builds from the repository root. Finance and Notes use the root context to compile the shared UI from the locked frontend dependencies; Oracle keeps the `plugins` context:

```sh
docker build -f plugins/finance/Dockerfile -t signaldeck-finance:1.3.0 .
docker build -f plugins/digital_oracle/Dockerfile -t signaldeck-digital-oracle:1.0.0 plugins
docker build -f plugins/notes/Dockerfile -t signaldeck-notes:1.3.0 .
```

Each image pins Python 3.14.0 and uv 0.9.8 by image digest and contains an independently frozen `uv.lock`. Direct application dependencies include MCP 1.26.0, FastAPI 0.136.3, Pydantic 2.12.5, SQLAlchemy 2.0.51, psycopg 3.3.4 and JSON Schema 4.26.0. MCP protocol is **2025-11-25**.

Finance and Notes require `PLUGIN_DATABASE_URL`, pointing to a separately owned PostgreSQL database/role. Neither falls back to Core's `DATABASE_URL`. Startup creates only that plugin's business tables and operation journal. Finance owns `reports`, `text_templates` and `market_quotes`; Notes owns `notes` and `note_provenance`; each owns its own `plugin_operations`. Oracle has no business persistence requirement. Existing Core business data is **not** migrated, reset or read by these services.

Finance and Notes images build `frontend/src/plugin-ui` using the same React, shadcn primitives and theme sources as the platform. Their Python runtime serves the packaged JS/CSS at `/ui`; it requires neither a running Core/frontend service nor Node. Generated assets live under `runtime/plugin_runtime/web/`, are excluded from Git, and are included in the plugin artifact digest.

Before starting Finance or Notes as a local Python process, build the shared assets from the repository root:

```sh
(cd frontend && pnpm install --frozen-lockfile && pnpm build:plugin-ui)
```

For a local Python process, run `uv sync --frozen` in the chosen project. Set `PYTHONPATH` to that project directory plus `plugins/runtime`, then use one of:

```sh
uv run uvicorn finance_plugin.main:create_app --factory --host 127.0.0.1 --port 8091 --no-access-log
uv run uvicorn oracle_plugin.main:app --host 127.0.0.1 --port 8092 --no-access-log
uv run uvicorn notes_plugin.main:create_app --factory --host 127.0.0.1 --port 8093 --no-access-log
```

Set `PLUGIN_ENDPOINT` to the exact reachable MCP URL including `/mcp/`. Finance's `PLUGIN_PAGE_URL` points to its independently served page, defaulting to `http://localhost:8091/`. `GET /release` supplies the complete installation descriptor; `GET /health` reports the running release. Install descriptors through Core's generic plugin catalog. A disabled or unavailable plugin does not need to be imported for Core history reads.

Oracle resolves its own optional `FRED_API_KEY` and `EDGAR_CONTACT_EMAIL` from the plugin's deployment environment, at its own I/O boundary. They are never returned in descriptors, MCP metadata or model messages. Scope references and grants carry no credentials. Production provider access was not exercised by local tests.

## Research source boundaries

Reddit RSS and JSON results apply the requested date bounds before retaining samples; missing or invalid publication dates cannot satisfy a bounded query. Revisions known to be newer than the cutoff are excluded. The public search is limited to its returned sample and is not a complete historical archive; current vote/comment counts do not establish past counts. Yahoo news excludes undated articles instead of assigning the query time as their publication time, and returns a warning with the excluded count even when other articles remain available.

Oracle's Treasury source reads monthly average interest rates by security category, under `macro_indicators`. It is not a maturity yield curve. Requests constrain record dates and retrieve newest records first; an `asOfDate` query warns that this dataset does not establish historical publication times or revision vintages. Series identities distinguish security type and description; selected-series lookups filter within a bounded paginated search before applying the result limit, and disclose incomplete coverage. SEC Form 4 summaries read the original XML behind an XSL display URL and contain non-derivative transactions only. An empty document does not produce a transaction, and derivative activity is explicitly outside that summary's coverage.

Kalshi uses its published fixed-point contract counts and dollar order-book prices without float conversion. The adapter reads `volume_fp`, `open_interest_fp` and `orderbook_fp`, converts NO bids into YES asks, and selects the best prices before applying the requested depth. An explicitly empty fixed-point side is not filled using a different legacy snapshot.

The real Yahoo fundamentals/insider methods remain unavailable. Finance now selects SEC companyfacts for its live `fundamentals_lookup`, with explicit cutoff, fiscal periods, accession revisions, calculation operands and evidence. Both Finance and Oracle require their own `EDGAR_CONTACT_EMAIL` deployment environment; Compose passes the configured value to both, never to the release descriptor. The deterministic provider remains an explicit test choice. Standard entity-wide concepts do not cover all segment/custom disclosures; capital-expenditure concepts retain their different scope, and missing short-term debt is not assumed to be zero.

Oracle adds `source_documents_lookup` for explicit URLs or bounded SEC discovery, preserving original URLs, publication metadata, document digest and located passages. HTML extraction excludes hidden inline XBRL and separates table cells. Documents over 8 MB, unsupported formats, unknown publication times and incomplete excerpts produce visible gaps. An arbitrary IR/policy URL is a user-selected source, not automatic proof of publisher authority. `prediction_events_lookup` uses at most three explicit event/contract selections, retains rule identity, status, deadline, outcome and quote metadata, and refuses historical comparison without a suitable quote timestamp and rule record. The older free-text lookup remains bounded discovery, not a complete thematic index. The yfinance options adapter remains optional and absent from the standard locked image; these workflows do not enable it by default.

`research_macro_evidence` preserves the original five FRED series by default, with up to five selected series and 50 observations. Requests use one bounded time budget and a vintage for the latest fully completed New York date within the cutoff. `periodEnd` remains the observation period; `availableByDate` means the selected version was available by that date's end, not its publication timestamp. Reports and monitoring check that separate upper bound without inventing a release time.

Finance exposes `research_scope_freeze`, `research_market_evidence`, `research_evidence_merge`, `research_report_compile` and `research_reports_create`. Source results enter the same closed, versioned evidence collection; models only propose claims, thresholds and qualitative explanations. The deterministic compiler recomputes accepted numerical claims, checks threshold provenance and emits one canonical body with readable source references. Report storage and download preserve that body. Valuations based on reported shares remain explicitly unverified estimates until intervening share changes can be reconciled. Ordinary `reports_create` retains its general-purpose behavior.

Finance 1.2.0 accepts optional bounded discussion records in the report compiler. Original opposing arguments, responses, risk assessments and adjudications remain separate. The compiler checks identities, opposing response targets, coverage and eligible evidence references, adding readable gaps without discarding the original records. Explicitly unresolved outcomes are valid; all qualitative statements remain unverified, and numerical assertions still require the existing numerical contract. Omitting discussion preserves the previous report output. See the [public discussion contract](../docs/writing-extensions.md#finance-研究争议合同); no Core, UI or database changes are required.

Finance 1.3.0 adds the read-only `price_events_lookup` tool. It applies closed daily K-line rules (new closing highs/lows, breakouts, gaps, large moves, gap fills, island reversals, moving-average/MACD/RSI/Bollinger signals, range contraction, inside bars, volume spikes, streaks and relative strength) to at most five granted symbols over completed New York sessions, and returns each symbol's latest price state with bounded events that echo their effective parameters. A session counts only after 16:30 New York time; an unfinished bar never produces an event. The existing indicator series computation is shared with `indicators_lookup` without changing its output. Results describe past prices only; they are not forecasts, backtests or trading signals. The tool reads daily bars only. Yahoo history is the current version rather than a point-in-time archive and its prices are split-adjusted but not dividend-adjusted, so an ex-dividend open can register as a down gap. See the [public contract](../docs/writing-extensions.md#finance-k-线事件合同).

The `monitor_begin`, `monitor_observe` and `monitor_report_attach` write tools use Finance's own transaction journal and new observation tables. Scope includes explicit source/event selections and rule versions; dynamic retrieval times do not change scope identity. New official facts, revised facts, selected numerical thresholds and prediction-contract changes have distinct meanings. Incomplete required coverage never replaces a valid baseline. See the [research implementation record](../docs/planning/research-upgrade-readiness.md) for validation and remaining source limitations.

## Frozen contracts and resource scopes

Tool IDs are qualified by owner: for example `signaldeck/finance/reports_create`, `signaldeck/digital-oracle/market_sentiment_lookup` and `example/notes/create`.

The descriptor's tool definitions are the sole source of `tools/list`, dispatch lookup, input validation and output validation. Schemas are a closed 2020-12 subset with explicit `unevaluatedProperties: false`. The wire representation omits nullable optional fields, represents decimal values as strings, and projects warning detail maps as key/value arrays. Date fields are ISO strings; typed provider projections validate dates before serialization. This wire contract replaces the previous nullable OpenAI argument declarations and host DTO representation.

| Tool | Arguments | Required resource and non-sensitive scope |
| --- | --- | --- |
| `example/notes/create` | `title`, `text`; optional `sourceKind`, `sourceNoteIds` | `notes-workspace`: `{"collection":"research"}` |
| `example/notes/search` | Optional `query`, `limit`, `includeDerived` | `notes-workspace`: `{"collection":"research"}` |
| `signaldeck/finance/market_data_quote_lookup` | `symbols` | `finance-market-data`: `{"allowedSymbols":["MSFT","AAPL"]}` |
| `signaldeck/finance/price_events_lookup` | `symbols`, `detectors`; optional `asOfDate`, `windowSessions` | `finance-market-data`: `allowedSymbols` covers `symbols` and any `relative_strength` benchmark |
| Other Finance market tools | See published contract | `finance-market-data`: `allowedSymbols` limits symbol arguments |
| `signaldeck/finance/reports_create` | `name`, `content` | No resource required; persists immutable Agent provenance from the call identity |

The Gateway sends only the granted resource scopes in `_meta["signaldeck/context"].resourceBindings`. Notes stores and filters the collection in business SQL; Finance rejects symbols outside its scope. Missing required grants are rejected at the MCP boundary. Report reads and the Finance business page are owned by Finance, not the Core API.

## Operations and upgrades

Each business invocation carries the exact four-field release identity in `_meta["signaldeck/release"]`: `pluginId`, `releaseId`, `artifactDigest`, `contractDigest`. A process rejects a different binding. All distributed files under the plugin and shared runtime directories determine artifact identity, including `VERSION`, code, web assets, Dockerfile, lockfiles and packaged documentation; only `__pycache__`, `.venv` and `.git` are excluded. Finance and Oracle also bind their resolved non-sensitive provider settings to that identity. The contract digest independently covers all advertised tool definitions. Packaged documentation changes therefore affect the artifact identity computed when a new process starts.

Release upgrades use a **new immutable artifact and endpoint**. Retain the old image/process and old endpoint while frozen Runs still reference them. Changing a running endpoint to a new release causes old requests to fail explicitly; it does not substitute new code. The independent upgrade test runs Notes 1.0.0 and 1.1.0 simultaneously, confirms distinct artifact identity, rejects a mismatched binding, and continues calls to the original release.

Notes writes and Finance Agent-report writes use a PostgreSQL transaction for the business effect and immutable operation result. An operation-scoped advisory lock prevents concurrent duplication. Reuse of an operation ID with different arguments, tool or scope is rejected. `signaldeck/operations/query` returns `unknown` while the effect transaction holds the lock, `succeeded` plus the saved result after commit, or authoritative `not_found` after rollback/absence. It also checks the stored tool grant and resource scope before exposing a result. This deduplication covers these database writes, not arbitrary remote-provider side effects.

Notes 1.2.0 adds explicit original/derived provenance and confirmed same-collection source references, committed atomically with notes and operation receipts. A new `note_provenance` sidecar table is initialized without altering or backfilling `notes`; historical records remain unclassified. Generic search defaults to including derived records, while the revised research package and workspace page explicitly default to excluding them. See the [public Notes contract](../docs/writing-extensions.md#notes-来源与检索合同) for fields and upgrade boundaries. This source revision does not deploy or convert an existing instance.

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
