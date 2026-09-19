# Workflow Packages

These standalone `signaldeck.workflowPackage/v2` examples are not platform components, bundled defaults or test fixtures ([decoupling principle](../docs/产品说明.md#工作流与平台解耦原则)). Import a selected file through Workflow Packages or the [public import API](../docs/工作流解耦方案.md#独立数据导入与分发), configure its resources, then choose a workflow in the task catalog and fill in its inputs.

| Package | Workflow (catalog name) | Result | Resources |
| --- | --- | --- | --- |
| [US equity research](us_equity_research.yaml) | `research` (美股多空研究) | Four analyst reports, a bounded bull/bear debate, independent risk review, a directional assessment and optional comparison with a supplied prior report, saved as a Finance report | Finance and Digital Oracle plugins; `finance-market-data`; `equity-research-model` |
| [US equity research](us_equity_research.yaml) | `monitor` (美股证据变化监测) | Frozen observations and explicit evidence comparisons; deep research only on an initial baseline or material change | Finance and Digital Oracle plugins; `finance-market-data`; `equity-research-model` |
| [Research notes](research_notes.yaml) | `research` (整理笔记) | Collection search, optional editing of conclusions and evidence-backed revisions, and an immutable note with source links | Notes plugin; `notes-workspace`; `research-model` |
| [Research notes](research_notes.yaml) | `capture` (保存原文) | Original text saved verbatim as an immutable note, without a model | Notes plugin; `notes-workspace` |
| [Watchlist K-line scan](watchlist_price_events.yaml) | `scan` (自选股 K 线扫描) | Low-frequency daily K-line events for every granted symbol, shown as a digest and saved as a Finance report when the newest completed session is the scan date and the window's event count reaches `minEvents` | Finance plugin 1.5.0 or later; `finance-market-data` |

The model-based workflows write in Chinese; a successful run confirms the data path, not the accuracy of the model's judgment ([verification boundary](../docs/产品说明.md#验证边界)).

## Watchlist K-line scan

Choose **自选股 K 线扫描** in the task catalog. The watchlist is the `allowedSymbols` scope of the `finance-market-data` connection: the scan covers every symbol there and fails with `price_events_watchlist_too_large` above 50 ([K-line contract](../docs/writing-extensions.md#finance-k-线事件合同)). The equity research workflows use the same connection, so every ticker added for research is scanned too. It needs Finance 1.5.0 or later and no model.

The `scan` node calls `price_events_lookup` without symbols and with five low-frequency rules fixed in the package: single-session large moves, volatility-scaled five-session moves, large moves given back, drawdowns of 20% from the 60-session closing high, and new 60-session closing highs or lows whose prior extreme is at least 20 sessions old. Edit the package to change them.

The `save` node stores the Chinese digest as a Finance report only when the newest completed session is the scan date and the event count reaches `minEvents` (default 1). On a market holiday, a weekend or before 16:30 New York time, the newest session is an earlier one, so the run shows the digest and saves nothing; this keeps a daily schedule from repeating the previous session. `windowSessions` (default 1) sets how many recent sessions to report; use 5 for a weekly run.

Create a repeat schedule for the workflow in the New York time zone on weekdays after 16:30, for example 16:45. Every fire is an ordinary run: its digest appears in the run history and its report, if any, opens from the result. SignalDeck sends no push notifications. Events describe past daily prices only.

## Configure resources

Both provided Compose stacks (`./start.sh` and `docker/compose.production.yml`) run a bootstrap step that registers the enabled plugins not yet installed and creates any missing default tool resource from [`docker/plugin-defaults.json`](../docker/plugin-defaults.json): `finance-market-data` (Finance, allowed symbols `MSFT` and `AAPL`) and `notes-workspace` (Notes, collection `research`). Independently deployed plugins need the same release descriptors and resources; see the [plugin guide](../plugins/README.md). Then:

- Create the model resource the package names, `equity-research-model` or `research-model`, with the provider's base URL and model ID, and enter its credential in the separate credential field, never in a package, prompt or resource scope. The dedicated equity connection lets its model service apply provider-native JSON output and its own reasoning settings without affecting other workflows; the packages carry no vendor-specific request options.
- Add every researched ticker to `finance-market-data.config.scope.allowedSymbols`; the default scope does not include the example's default `NVDA`.
- Live SEC data needs `EDGAR_CONTACT_EMAIL` in both the Finance and Oracle deployment environments, and FRED series need `FRED_API_KEY` in Oracle's; neither belongs in workflow input or YAML ([plugin guide](../plugins/README.md)).

## US equity research

`research` borrows the analyst, bull/bear discussion and final judgment structure from [TradingAgents](https://github.com/TauricResearch/TradingAgents) without reproducing it. It freezes its information cutoff, then collects structured SEC financial facts, completed daily market bars, dated news, FRED macro series and located original-document passages into one collection. Four analysts (market, company, macro and news/policy) read that collection, with at most two nodes running at once. Each side proposes at most three numbered arguments and answers every opposing argument once; the risk review and the adjudication address each argument by its identifier.

Finance validates the proposed claims and thresholds deterministically and saves one canonical body, which is also the stored and downloaded report; the model's narrative and stance stay marked as unverified inference. Contracts: [research evidence](../docs/writing-extensions.md#financeoracle-研究合同) and [discussion](../docs/writing-extensions.md#finance-研究争议合同).

```json
{
  "symbol": "NVDA",
  "asOfDate": "2026-09-15",
  "horizonMonths": 3,
  "question": "综合公司财务、宏观环境、新闻与美国政策，判断未来三个月偏多、偏空、中性还是证据不足，并说明原因和失效条件。",
  "supportingMaterials": []
}
```

The date above is an example, not a moving default. `asOfDate` has no default: pass the US market (New York) date. A later date, such as a local date already a day ahead, is rejected when the scope is frozen (`research_date_is_in_the_future`). A new draft defaults to `NVDA` and three months (`horizonMonths` 1–24).

- `supportingMaterials` holds up to eight items with `category` (`宏观数据`, `公司财报`, `新闻`, `美国政策` or `其他`), `title`, `publishedDate`, `source` and `content`. Give a source URL or clear attribution, keep the reporting period and units in `content`, and never put credentials there; the report treats these items as unverified user-supplied evidence.
- `sourceUrls` selects up to five official documents instead of automatic SEC discovery, and `macroSeriesIds` up to five FRED series.
- `lookbackDays` (1–31, default 7) and `statementLimit` (1–12, default 4) bound the market/news history and the number of financial records. A longer judgment horizon does not turn a short collection window into long-term evidence, and neither input extends provider history or adds model calls.
- `includeSocial`, `includeInsider` and `includePrediction` are explicit opt-ins that default to off. Prediction research also needs up to three `events`, each with `venue` (`polymarket` or `kalshi`), the exact event or contract, a hypothesis and a reason. Missing optional evidence is disclosed without replacing the base research.
- `previousReport` takes a pasted earlier report with its subject, date, horizon, conclusion and sources. Only the final adjudication compares it, after the independent stages, separating new facts, corrected facts and changed assumptions or explaining why the reports are not comparable. The workflow never fetches earlier runs or keeps implicit memory.

The report keeps SEC facts with their actual periods and filing versions, keeps cumulative and quarterly cash flows apart, treats news summaries as summaries rather than full policy text, and labels valuations based on reported shares as unverified estimates. The workflow does not trade, manage holdings, backtest or assign calibrated win probabilities; other source limits are listed under [research source boundaries](../plugins/README.md#research-source-boundaries).

### Explicit monitoring

`monitor` (美股证据变化监测) takes a `monitorKey` and a closed `scope`: symbol and CIK, research question and horizon, rule version, selected sources with freshness limits, optional events and explicit numerical change `rules`. It has no date input and reads no earlier report. Each fire freezes a new cutoff with `monitor_begin` and compares the sources selected in `scope.sources` with the last valid baseline of the same scope; other collected material never decides freshness or change.

Only an initial baseline or a material change runs the deep research, through the same bounded discussion and canonical report path as `research`, and the report is bound to that exact observation. Unchanged evidence skips it; invalid required evidence neither triggers research nor replaces the baseline. Market and prediction quotes trigger research only through configured `rules`; prediction rule, status and expiry changes are reported apart from price changes, and probabilities are never compared across incompatible rules. Changing the scope or rules (with a new `ruleVersion`) starts a new baseline, while retrieval times, ordering and duplicate collection never trigger research. The window is fixed at seven days of market/news history and the latest four financial records because the public monitoring scope has no window field. Storage and baseline rules are in the [data model](../docs/data-model.md#插件业务数据).

## Research notes

`research` (整理笔记) searches the collection for at most 20 matching notes; `includeDerived` defaults to false so earlier summaries are not recycled as new evidence. The editor receives the title, the query, the current text and the retrieved notes, and writes four sections: current conclusions, changes and reasons, questions requiring verification, and sources and coverage. It stays on the title's topic even when the text is empty and reports an explicit gap when nothing relevant is found. An explicit later correction of an earlier estimate is recorded as a revision with evidence; incompatible claims without a supported correction remain unresolved. Notes has no event-date field, so the note uses only dates or chronology stated in the text, never ID or search order.

```json
{
  "title": "Experiment observations",
  "text": "The second run completed with the same inputs. The timing difference remains unexplained.",
  "query": "experiment",
  "summarize": true
}
```

## Optional read caching

All packages leave `toolCache` empty, so new runs, reruns and scheduled runs request fresh results; a restored run reuses its own confirmed results regardless. To opt a read tool into cross-run caching, add a policy under its Agent, for example on the Notes `find_notes` Agent:

```yaml
toolCache:
  example/notes/search:
    ttlSeconds: 60
    scope: resource
    key: release_input_resources
```

The [cache policy contract](../backend/app/domain/tool_contracts.py) permits a TTL from 1 to 86400 seconds, resource scope and a key derived from the frozen release, input and resource bindings. The tool must also be listed in the Agent's `tools`, and write tools cannot be cached. Choose a TTL the data's freshness allows; the example may reuse a collection search up to 60 seconds old.
