# Workflow Packages

These packages use `signaldeck.workflowPackage/v2`. Import a YAML file through Workflow Packages, configure its resources, then choose a workflow and supply its input JSON. Each run records the selected package revision and plugin release. The same definition is used by the editor and YAML import.

| Package | Workflow | Result | Resources |
| --- | --- | --- | --- |
| [Market advisory research](tradingagents_advisory_research.yaml) | `research` | Shared quotes, history and news evidence, parallel opportunity/risk assessments, and a Finance report with reasons and counterevidence | Finance plugin; `finance-market-data`; `research-model` |
| [Digital Oracle research](digital_oracle_researcher.yaml) | `research` | Parallel specialist research, cross-source checks and a Finance report identifying conclusions, counterevidence and unresolved gaps | Digital Oracle and Finance plugins; `research-model` |
| [US equity research](us_equity_research.yaml) | `research` | Four analyst reports, a bounded bull/bear debate, independent risk review, a directional assessment and optional comparison with a supplied prior report | Digital Oracle and Finance plugins; `finance-market-data`; `equity-research-model` |
| [Research notes](research_notes.yaml) | `research` | Collection search, optional editing of conclusions and evidence-backed revisions, and an immutable note with source links | Notes plugin; `notes-workspace`; `research-model` |
| [Research notes](research_notes.yaml) | `capture` | Original text saved as an immutable note | Notes plugin; `notes-workspace` |

Finance owns report storage and its report page. Notes owns the research collection. Oracle provider availability depends on its independent deployment configuration; unavailable evidence must be identified in the generated research. Research workflows do not place orders.

## Independent, repeatable methods

Each preset is an independent use case. Its business inputs, research roles, prompts, dependencies and result presentation live in YAML and use the existing public package, tool and presentation contracts. Adding or updating these packages requires no Core or frontend business code. SignalDeck remains a general workflow execution platform.

The model-based research presets request Chinese reports that distinguish facts from inference, retain source dates and attribution, explain counterevidence, and identify missing or incomparable data. Repeated citations of the same source do not count as independent corroboration. Explicit corrections are distinguished from unresolved conflicts. Successful execution and schema validation confirm the data path; they do not establish the accuracy of a model's judgment.

The three Finance-report workflows accept an optional `previousReport`. Paste the earlier report, including its subject, date, scope or horizon, conclusion and sources. Independent research stages receive only this run's inputs and evidence; the final editor compares the supplied report afterward. It must distinguish new facts, corrected facts and changed assumptions, and explain when the reports cannot be compared. No prior report means no historical comparison baseline. The workflow does not fetch previous runs or maintain implicit memory; repeated or scheduled launches keep the supplied input until it is explicitly changed.

## US equity research

This independent use case borrows the analyst, bull/bear discussion and final judgment structure from [TradingAgents](https://github.com/TauricResearch/TradingAgents). Its finite DAG runs four independent analysts (market, company, macro and news/policy), with at most two nodes executing concurrently, builds both cases, lets each side respond once, performs an independent risk review, then records the final assessment in Finance. All business prompts, topology, input fields and result presentation belong to this package; it adds no Core or frontend business logic.

Choose **美股多空研究** in the task catalog. Configure `equity-research-model` as a model resource and include the chosen ticker in `finance-market-data.config.scope.allowedSymbols`. This separate connection can use provider-native JSON output and its own reasoning settings without changing other workflows. Provider settings belong to the model service connection; the package contains no vendor-specific request options. Oracle reads `FRED_API_KEY` and `EDGAR_CONTACT_EMAIL` from its own deployment environment; the latter is the operator's contact email used in SEC request identification. Neither belongs in workflow input or YAML.

The report includes the analysis date and horizon, bullish/bearish/neutral/insufficient-evidence stance, reasons, counterevidence, invalidation conditions, data gaps, evidence confidence and `changes` relative to a supplied prior report. The comparison is also included in the saved report body. Evidence confidence is not a calibrated probability of profit. The workflow preserves source warnings and partial findings when an analyst cannot complete; missing critical evidence can prevent a directional conclusion.

Risk review and the final decision also receive the original supplemental materials, retaining source order for unit and citation checks. A previous report only enters the final comparison. Read-only model nodes allow at most two attempts within their existing deadline; the report writer does not restart a new write attempt this way. Output must still pass the platform's unchanged JSON and schema validation.

Current sources have different coverage: Finance provides price/history/indicators and news metadata or summaries; Oracle provides FRED observations and SEC filing discovery. Filing links are not a substitute for reading a financial statement, and news summaries do not establish the full text or legal effect of a policy. Optional `supportingMaterials` accepts explicitly attributed financial excerpts, macro releases and policy materials; these remain supplied evidence unless independently checked. Model knowledge must not fill missing current facts.

This package does not execute trades, adjust holdings, backtest, add implicit memory or register another execution engine. Reruns retrieve fresh available tool data while preserving the explicit input cutoff; updating the cutoff or supplemental material requires a new input. FRED series dates are observation periods, not release timestamps.

## Configure resources

Install the relevant release descriptors from each plugin's `/release` endpoint. Plugin deployment and resource scopes are described in [the plugin guide](../plugins/README.md).

Create `research-model` for the original research packages, or `equity-research-model` for US equity research, with the provider's base URL and model ID. Enter its credential in the separate credential field; do not put credentials in a package, prompt or resource scope. The `capture` workflow does not use a model resource.

Create these tool resources when using the corresponding package:

```json
{
  "resourceId": "finance-market-data",
  "kind": "tool",
  "config": {
    "name": "Research market data",
    "pluginId": "signaldeck/finance",
    "scope": {"allowedSymbols": ["MSFT", "AAPL"]},
    "maxConcurrentCalls": 4,
    "requestsPerSecond": 5
  }
}
```

```json
{
  "resourceId": "notes-workspace",
  "kind": "tool",
  "config": {
    "name": "Research collection",
    "pluginId": "example/notes",
    "scope": {"collection": "research"},
    "maxConcurrentCalls": 4,
    "requestsPerSecond": 5
  }
}
```

## Launch inputs

Market advisory `research`:

```json
{
  "symbols": ["MSFT", "AAPL"],
  "question": "Compare the current observations and identify the evidence still needed for a research decision.",
  "includeRisk": true
}
```

Setting `includeRisk` to `false` skips the independent risk branch; the report still states visible evidence limitations. Both branches reuse the same analyst definition and shared evidence, avoiding duplicate collection. The report identifies per-symbol findings, opposing evidence and observable conditions that would change the assessment. History and news coverage does not establish company financial health or policy text. Add `previousReport` only when an earlier report should be compared. Core does not infer business incompleteness from these inputs.

Digital Oracle `research`:

```json
{
  "question": "What do current macro conditions and available company evidence imply for Microsoft? Distinguish facts, inference and unavailable sources."
}
```

Optional `asOfDate` specifies a `YYYY-MM-DD` cutoff; without it, the report labels the dates of the data actually obtained. Optional `supportingMaterials` is a text field for excerpts with source, publication date and units. A URL alone is not evidence that its contents were read. Optional `previousReport` is used only by the final editor. SEC discovery results remain filing references rather than financial-statement text; FRED observation periods remain distinct from publication dates. Unknown units, unavailable sources and incompatible periods must remain visible in the report.

US equity `research` (the date is an explicit example, not a moving default):

```json
{
  "symbol": "NVDA",
  "asOfDate": "2026-09-15",
  "horizonMonths": 3,
  "question": "综合公司财务、宏观环境、新闻与美国政策，判断未来三个月偏多、偏空、中性还是证据不足，并说明原因和失效条件。",
  "supportingMaterials": []
}
```

Each optional material has `category` (`宏观数据`, `公司财报`, `新闻`, `美国政策` or `其他`), `title`, `publishedDate`, `source` and `content`. Use a source URL or clear attribution, retain the reporting period and units in `content`, and never put credentials in these fields. A fresh task draft defaults to NVDA and three months; the analysis date must be supplied explicitly using the US market date. A local date that is already tomorrow in the US must not request an unavailable future FRED vintage.

Research notes `research`:

```json
{
  "title": "Experiment observations",
  "text": "The second run completed with the same inputs. The timing difference remains unexplained.",
  "query": "experiment",
  "summarize": true
}
```

The editor uses four sections: current conclusions, changes and reasons, questions requiring verification, and sources and coverage. An explicit later correction of an earlier estimate is recorded as a revision with evidence; incompatible claims without a supported correction remain unresolved. Notes has no independent event-date field, so the report uses only dates or chronology stated in the text, never ID or search order. Search is limited to 20 matching notes; `includeDerived` defaults to false to avoid recycling summaries as new evidence.

New drafts default `summarize` to true. Setting it to false preserves the original text through an explicit missing-output fallback, while saving a derived note linked to the retrieved sources. Runtime inputs are not silently filled from draft defaults. To archive original material without configuring a model, select `capture`:

```json
{
  "title": "Experiment observations",
  "text": "The second run completed with the same inputs. The timing difference remains unexplained."
}
```

## Optional read caching

All packages leave `toolCache` empty. New runs, reruns and scheduled runs therefore request fresh results by default. A restored run can reuse its own confirmed results independently of this setting.

To opt a selected read tool into cross-run caching, add a policy under that Agent, for example on the Notes `find_notes` Agent:

```yaml
toolCache:
  example/notes/search:
    ttlSeconds: 60
    scope: resource
    key: release_input_resources
```

The [cache policy contract](../backend/app/domain/tool_contracts.py) permits a TTL from 1 to 86400 seconds, resource scope and a key derived from the frozen release, input and resource bindings. The tool must also be selected in the Agent's `tools`. Write operations cannot enable result caching. Cache evidence records the source run and operation, acquisition time, expiration and hit status. Choose a TTL that is acceptable for the data's freshness; the example above may reuse an older collection search for up to 60 seconds.

## Maintaining the examples

The YAML files are optional workflow data distributed outside the Core executable artifact. The local Compose stack mounts them read-only; a direct API process imports them only when `SIGNALDECK_WORKFLOW_DATA_DIR` selects a directory. Startup and API `missing_only` imports atomically preserve existing package keys, while explicit `update` imports may advance the current revision. Imported records use the same parser, canonical source and immutable revision checks as editor saves. Reading saved definitions does not require the source directory or a running business plugin. Startup options are documented in the [project entry](../README.md#快速开始); the batch API is specified in the [independent import contract](../docs/工作流解耦方案.md#独立数据导入与分发).

After editing a YAML example, regenerate only the [machine contracts](contracts.json) from `backend/`:

```sh
uv run python ../demo/sync_seeds.py
uv run pytest tests/test_target_seeds.py tests/test_dag_compiler.py tests/test_demo_presentation.py tests/test_demo_workflow_dataflow.py -q
```

The contracts lock content hashes, tool and resource identities, node order, merged dependencies and edge origins. The tests also validate each deterministic Agent transformation and presentation binding against the independently published tool schema, and verify atomic, non-overwriting missing-only imports in PostgreSQL. The generator never embeds workflow sources into Core Python or app resources.
