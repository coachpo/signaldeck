# Workflow Packages

These packages use `signaldeck.workflowPackage/v2`. Import a YAML file through Workflow Packages, configure its resources, then choose a workflow and supply its input JSON. Each run records the selected package revision and plugin release. The same definition is used by the editor and YAML import.

| Package | Workflow | Result | Resources |
| --- | --- | --- | --- |
| [Market advisory research](tradingagents_advisory_research.yaml) | `research` | Fresh quotes, parallel opportunity/risk assessments, and an immutable Finance report | Finance plugin; `finance-market-data`; `research-model` |
| [Digital Oracle research](digital_oracle_researcher.yaml) | `research` | Parallel specialist research and a cross-source Finance report | Digital Oracle and Finance plugins; `research-model` |
| [Research notes](research_notes.yaml) | `research` | Collection search, optional model editing, and an immutable note | Notes plugin; `notes-workspace`; `research-model` |
| [Research notes](research_notes.yaml) | `capture` | Original text saved as an immutable note | Notes plugin; `notes-workspace` |

Finance owns report storage and its report page. Notes owns the research collection. Oracle provider availability depends on its independent deployment configuration; unavailable evidence must be identified in the generated research. Research workflows do not place orders.

## Configure resources

Install the relevant release descriptors from each plugin's `/release` endpoint. Plugin deployment and resource scopes are described in [the plugin guide](../plugins/README.md).

Create `research-model` as a model resource with the provider's base URL and model ID. Enter its credential in the separate credential field; do not put credentials in a package, prompt or resource scope. The `capture` workflow does not use a model resource.

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

Setting `includeRisk` to `false` skips the risk branch. The summary explicitly records the missing review. Both branches reuse the same analyst definition with different perspective inputs; their dependencies belong to the workflow nodes.

Digital Oracle `research`:

```json
{
  "question": "What do current macro conditions and available company evidence imply for Microsoft? Distinguish facts, inference and unavailable sources."
}
```

Research notes `research`:

```json
{
  "title": "Experiment observations",
  "text": "The second run completed with the same inputs. The timing difference remains unexplained.",
  "query": "experiment",
  "summarize": true
}
```

Setting `summarize` to `false` preserves the original text through an explicit missing-output fallback. To save without configuring a model, select `capture`:

```json
{
  "title": "Experiment observations",
  "text": "The second run completed with the same inputs. The timing difference remains unexplained."
}
```

## Optional read caching

All three packages leave `toolCache` empty. New runs, reruns and scheduled runs therefore request fresh results by default. A restored run can reuse its own confirmed results independently of this setting.

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

The YAML files are the source of the bundled startup packages. Startup inserts missing package keys and preserves operator edits under an existing key. The shipped source is embedded in the Core artifact so reading presets requires neither a filesystem checkout nor a running business plugin. Database revisions use the same canonical source representation as editor saves.

After editing a YAML example, regenerate the bundled sources and [machine contracts](contracts.json) from `backend/`:

```sh
uv run python ../demo/sync_seeds.py
uv run black --config pyproject.toml app/infrastructure/package_seeds.py ../demo/sync_seeds.py
uv run pytest tests/test_target_seeds.py tests/test_dag_compiler.py -q
```

The contracts lock content hashes, tool and resource identities, node order, merged dependencies and edge origins. The tests also validate each deterministic Agent transformation against its independently published tool schema and verify atomic, non-overwriting seed installation in PostgreSQL.
