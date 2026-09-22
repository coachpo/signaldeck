# Independent business plugins

These services are separately built Python artifacts. No service imports the Core `app` package or reads Core tables. `runtime/plugin_runtime` is a small, source-distributed library for MCP transport, release identity, wire projection and the operation journal; the single application image carries one copy of it beside each plugin's own source, frozen lock file and virtual environment. The public contracts, including release identity and write recovery, are in [writing-extensions.md](../docs/writing-extensions.md); plugin upgrades follow its [upgrade rule](../docs/writing-extensions.md#独立接入与升级).

| Artifact | Business ownership | Additional surface |
| --- | --- | --- |
| `finance` | Templates and Reports; market quotes, history, OHLCV, indicators, K-line events, fundamentals, news, social sentiment, insider data, holders and analyst estimates; research evidence, report compilation and monitoring | [Report workspace](finance/README.md) at `/`, with its own `/api/templates` and `/api/reports`; routers in `finance/finance_plugin/api/`, business tables in `finance/finance_plugin/models/`, page in `finance/web/` |
| `digital_oracle` | Prediction markets, SEC filings, market sentiment, macro rates, crypto derivatives, CFTC positioning and options providers; source documents, prediction events and macro evidence for research | None; stateless |
| `notes` | Non-financial immutable notes and collection search | [Read-only workspace](notes/README.md) at `/`, with its own read-only `/api/collections`, `/api/notes` and `/api/note` |

Each plugin runs as its own container and service from the shared image, selected by the role argument `finance`, `notes` or `digital-oracle`, and serves MCP at `/mcp/`, its descriptor at `GET /release` and its running release at `GET /health`. Unavailable Oracle providers report their absence; no synthetic upstream evidence is generated. The files under a plugin's directory and `plugins/runtime/` make up that plugin's [artifact digest](../docs/writing-extensions.md#发布描述), so editing anything there, including the Finance and Notes READMEs, produces a new release identity. Sharing one image does not couple those identities: each digest still covers only its own directory plus the shared runtime.

## Build and run

One build from the repository root produces the image that serves every plugin role:

```sh
docker build -t signaldeck:local .
```

Run a plugin by passing its role as the container command, for example `docker run signaldeck:local notes`. Each role starts from its own virtual environment on port 8000.

Finance and Notes require `PLUGIN_DATABASE_URL`, pointing to a separately owned PostgreSQL database and role; neither falls back to Core's `DATABASE_URL`. Startup creates only that plugin's missing business tables and its `plugin_operations` journal; table ownership is listed in [data-model.md](../docs/data-model.md#插件业务数据). Oracle has no persistence.

The image builds `frontend/src/plugin-ui` with the platform's React, shadcn primitives and theme sources. The Finance and Notes roles serve the packaged JS/CSS at `/ui` without a running Core, frontend service or Node. The generated assets live in the Git-ignored `runtime/plugin_runtime/web/` and are part of the artifact digest. Before starting Finance or Notes as a local Python process, build them from the repository root:

```sh
(cd frontend && pnpm install --frozen-lockfile && pnpm build:plugin-ui)
```

For a local Python process, run `uv sync --frozen` in the chosen project. Set `PYTHONPATH` to that project directory plus `plugins/runtime`, then use one of:

```sh
uv run uvicorn finance_plugin.main:create_app --factory --host 127.0.0.1 --port 8091 --no-access-log
uv run uvicorn oracle_plugin.main:app --host 127.0.0.1 --port 8092 --no-access-log
uv run uvicorn notes_plugin.main:create_app --factory --host 127.0.0.1 --port 8093 --no-access-log
```

Set `PLUGIN_ENDPOINT` to the exact reachable MCP URL, including `/mcp/`. `PLUGIN_PAGE_URL` sets the Finance and Notes page base. Both Compose files set it to `/apps/{artifactDigest}/`: the descriptor replaces the placeholder with the hexadecimal artifact digest, which is also the plugin's mount key, so the page opens inside the platform. The standalone defaults `http://localhost:8091/` (Finance) and `http://localhost:8093/` (Notes) are for plugin development only.

Provider settings come from the plugin's deployment environment and are read only at its own I/O boundary; the secrets never appear in descriptors, MCP metadata, scopes or model messages:

- `EDGAR_CONTACT_EMAIL` (Finance and Oracle): the contact SEC EDGAR requires. Without it, SEC-backed lookups report the source as unavailable or not configured instead of returning data. Both Compose files pass it to both plugins.
- `FRED_API_KEY` (Oracle): FRED access. Without it, FRED lookups report that the source is not configured.
- `DIGITAL_ORACLE_PROVIDER_TIMEOUT` (Oracle, default 5 seconds): the upstream request timeout of the seven provider lookup tools and of the SEC filing discovery in `source_documents_lookup`; a selected-series Treasury lookup spends it as one budget across its pages. Document downloads, `prediction_events_lookup` and `research_macro_evidence` use fixed limits. Only the local Compose passes it.
- The remaining settings, which neither Compose file passes: Finance's `QUOTE_PROVIDER_BACKEND` (`yahoo`, or `deterministic` for tests), `QUOTE_PROVIDER_TIMEOUT` and the `FINANCE_*` news and Reddit options in `finance/finance_plugin/config.py`; Oracle's per-source `DIGITAL_ORACLE_*_ENABLED` switches and default item limits in `digital_oracle/oracle_plugin/settings.py`; and `ALPHA_VANTAGE_API_KEY`, which Finance reads only when `FINANCE_NEWS_PROVIDER_ORDER` includes `alpha_vantage`.

Finance and Oracle bind their non-secret provider settings, such as `DIGITAL_ORACLE_PROVIDER_TIMEOUT`, into the artifact digest, so changing them also produces a new release.

## Research source boundaries

Reddit RSS and JSON results apply the requested date bounds before retaining samples; missing or invalid publication dates cannot satisfy a bounded query, and revisions known to be newer than the cutoff are excluded. The public search returns a limited sample, not a complete historical archive, and current vote or comment counts do not establish past counts. Yahoo news excludes undated articles instead of stamping them with the query time, and warns with the excluded count even when other articles remain.

Finance reads Yahoo quotes, history and OHLCV through the pinned `yfinance` library and keeps Yahoo's own bar labels: daily bars at the regular session start, weekly and monthly bars at exchange-local midnight. An OHLCV read requests Yahoo data up to the present and trims the window itself, because yfinance serves windows that ended in the past from an in-process cache. Yahoo news keeps Finance's own search client for the same reason: yfinance's search answers repeated identical queries from that cache. Insider rows, holders and analyst estimates come from the same library through requests it does not cache; each is the provider's current snapshot, without earlier versions, so none can describe a past date. Insider rows carry transaction dates without filing times, and the holder tables list only the largest holders from their latest periodic reports.

Finance's live `fundamentals_lookup` reads SEC companyfacts with an explicit cutoff, fiscal periods, accession revisions, calculation operands and evidence; the deterministic provider is an explicit test choice. Standard entity-wide concepts do not cover all segment or custom disclosures, capital-expenditure concepts keep their different scope, and missing short-term debt is not assumed to be zero. Yahoo supplies Finance's analyst consensus through `analyst_estimates_lookup` and insider transactions through `insider_data_lookup`; Yahoo fundamentals stay unused.

Oracle's Treasury source reads monthly average interest rates by security category under `macro_indicators`; it is not a maturity yield curve. Requests constrain record dates and read the newest records first, and an `asOfDate` query warns that this dataset has no historical publication times or revision vintages. Series identities distinguish security type and description; selected-series lookups filter within a bounded paginated search before applying the result limit and disclose incomplete coverage.

Oracle's FRED adapter reads observations newest first within the requested date window and splits the call's item limit across the selected series; `asOfDate` bounds both the observation end date and the revisions known on that date. Titles and units come from the FRED series metadata. The returned `date` is the observation period, not a publication date, and no release-time field is returned, so callers keep frequency, seasonal-adjustment and annualization distinctions themselves.

SEC Form 4 summaries read the original XML behind an XSL display URL and cover non-derivative transactions only; an empty document produces no transaction. Kalshi contract counts and order-book prices use the published fixed-point fields without float conversion; NO bids become YES asks before the requested depth is applied, and an explicitly empty fixed-point side is not filled from another snapshot.

`source_documents_lookup` reads explicit URLs or bounded SEC discovery and keeps original URLs, publication metadata, the document digest and located passages. HTML extraction excludes hidden inline XBRL and separates table cells. Documents over 8 MB, unsupported formats, unknown publication times and incomplete excerpts produce visible gaps. An arbitrary IR or policy URL is a user-selected source, not proof of publisher authority. `prediction_events_lookup` takes at most three explicit event or contract selections, keeps rule identity, status, deadline, outcome and quote metadata, and refuses historical comparison without a suitable quote timestamp and rule record. The free-text `prediction_markets_lookup` is bounded discovery, not a complete thematic index. `options_lookup` reads Yahoo option chains through `yfinance`; they carry implied volatility but no other Greeks, so `includeGreeks` fills only implied volatility.

`research_macro_evidence` reads FRED only: five default series, or at most five explicit series, with up to ten observations each within one 15-second request budget. Its vintage is the last complete New York date before the cutoff. `periodEnd` remains the observation period; `availableByDate` means the selected version was available by the end of that date, not its publication time. Without `FRED_API_KEY` it returns a gap.

`price_events_lookup` applies Finance's closed daily K-line rules to granted symbols, or scans the whole granted watchlist (at most 50 symbols) when `symbols` is omitted, over the same provider daily bars as `market_data_ohlcv_lookup`; its price basis, rules, digest and limitations are defined by the [public contract](../docs/writing-extensions.md#finance-k-线事件合同).

## Resource scopes

Grants and scope binding follow the [resource contract](../docs/writing-extensions.md#资源凭据与业务数据): calls without the required grant are rejected at the MCP boundary, and each plugin enforces its scope in its own business logic. The runtime turns every tool-call rejection or failure into a generic MCP tool error without the plugin's code, which Core records as `plugin_operation_error`.

| Resource | Owner | Scope | Required by | Enforcement |
| --- | --- | --- | --- | --- |
| `finance-market-data` | `signaldeck/finance` | `allowedSymbols`: unique symbols | `market_data_quote_lookup`, `market_data_history_lookup`, `market_data_ohlcv_lookup`, `indicators_lookup`, `fundamentals_lookup`, `news_lookup`, `social_sentiment_lookup`, `insider_data_lookup`, `holders_lookup`, `analyst_estimates_lookup`, `price_events_lookup`, `research_market_evidence` | Every requested symbol, including a `relative_strength` benchmark, must be allowed, otherwise the plugin rejects the call with `finance_symbol_not_granted`; `price_events_lookup` without `symbols` scans the whole list, at most 50 |
| `notes-workspace` | `example/notes` | `collection` | `create`, `search` | Notes are stored in and searched within that collection only |

The other Finance tools (`reports_lookup`, `reports_create`, `research_scope_freeze`, `research_evidence_merge`, `research_report_compile`, `research_reports_create`, `monitor_begin`, `monitor_observe`, `monitor_report_attach`) and all ten Oracle tools require no resource. Bootstrap creates missing resources with the default scopes in [`docker/plugin-defaults.json`](../docker/plugin-defaults.json).

## Local validation

From `backend`:

```sh
uv run pytest tests/test_independent_plugins.py -q
```

These tests run the plugins against isolated PostgreSQL databases through a real MCP Streamable HTTP client and server; they call no model service or paid provider. The Finance and Notes page tests are described in their READMEs.

`plugins/tests/image_smoke.py` checks the three plugin roles of the built image. It runs `signaldeck:local`, or the tag in `SIGNALDECK_IMAGE`, and expects a local PostgreSQL resolved like the [backend test database](../CONTRIBUTING.md#测试数据库与-e2e-环境) that the containers reach through `host.docker.internal`, and the backend virtual environment. From the repository root:

```sh
backend/.venv/bin/python plugins/tests/image_smoke.py
```

It creates UUID-named databases, starts one container per role, checks Finance HTTP compilation plus MCP report write and query and Notes MCP write and query, then removes its containers and databases. CI runs neither this check nor the Finance-only tests.
