# Temporal candidate integration probe

This is evidence for the engine comparison required by frozen SD-TARGET-001
`bca05dcd666e96561426224b89b0e06aed186a22`, T06/A16. It is an isolated
experiment, not SignalDeck implementation or full acceptance of A01–A18.

## Pinned combination

- Python 3.13.13 (actual execution environment).
- `pydantic-ai-slim[temporal]==2.40.0`.
- `temporalio==1.32.0`.
- `jsonschema==4.26.0`.
- Temporal CLI 1.8.3, embedding Server 1.31.2 and UI 2.50.1.
- `requirements.lock` fixes transitive dependencies with package hashes.

Versions were checked against the official
[PyPI Temporal package](https://pypi.org/project/temporalio/),
[Pydantic AI package](https://pypi.org/project/pydantic-ai-slim/), and
[Temporal CLI release](https://github.com/temporalio/cli/releases/tag/v1.8.3).
The CLI dev server uses its own temporary SQLite database and is **only** a
local candidate test. Production PostgreSQL Temporal deployment was not tested.

## Reproduce

From the repository root, on macOS arm64:

```bash
uv venv /tmp/sd-temporal-probe-venv --python 3.13.13
uv pip install --python /tmp/sd-temporal-probe-venv/bin/python --require-hashes \
  -r backend/experiments/engines/temporal/requirements.lock
curl -fsSL https://github.com/temporalio/cli/releases/download/v1.8.3/temporal_cli_1.8.3_darwin_arm64.tar.gz \
  -o /tmp/sd-temporal-cli.tar.gz
mkdir -p /tmp/sd-temporal-bin
tar -xzf /tmp/sd-temporal-cli.tar.gz -C /tmp/sd-temporal-bin
TEMPORAL_CLI=/tmp/sd-temporal-bin/temporal \
  /tmp/sd-temporal-probe-venv/bin/python backend/experiments/engines/temporal/probe.py
```

On another platform, use the corresponding 1.8.3 CLI release asset. The probe
requires unused port 17233 and refuses to reuse a listener. It creates and stops
only its own server and worker subprocesses, including the worker deliberately
killed with SIGKILL. No existing application database or paid model is used.
Temporary files are retained so the printed `root` path contains the independent
I/O ledger, workflow histories, server/worker logs and `evidence.json`.

## Observed results

Final execution on 2026-09-08 exited **0**, with evidence at
`/var/folders/mx/ql1rs0s54k9d443xmlkc8_hm0000gn/T/sd-temporal-probe-28hkhfcq/`.
The assertions and event records establish these narrower results:

| Scenario | Observed result | Ownership |
| --- | --- | --- |
| Dynamic tool schema and qualified identities | A single registered dynamic gateway exposes two `search` tools using distinct aliases; minimum constraints differ per concurrent Run and are preserved in model declarations | Pydantic AI dynamic toolset plus platform-owned contract/alias map |
| Parallel Run isolation and freshness | Concurrent Runs with values 13 and 29 receive only their own tool results; every new Run invokes model/tools anew | Native independent histories; gateway has no cross-Run cache |
| DAG readiness | B/C overlap after A; E starts after B while C is unfinished; D waits for C | Workflow code expresses dependencies; engine schedules activities |
| Agent call recovery | SIGKILL after model step 0 and tool 0 are confirmed; restart preserves both, retries interrupted model step 1, completes tool 1 and model step 2 | Native Temporal history through `TemporalDurability` |
| Successful sibling recovery | Parent Workflow starts Agent Child Workflow plus sibling activity; sibling executes once across worker interruption | Native parent/child/activity histories |
| Frozen plugin recovery | New artifact appears during interruption; restarted invocation still uses its frozen digest | Platform-owned digest resolver, tested with fake artifact files |
| Missing plugin/core binding | Unavailable digest fails visibly; no successful tool I/O recorded | Platform-owned pre-I/O validation |
| Input schema and grants | Invalid minimum and empty grants fail before tool I/O | Gateway/schema boundary logic |
| Duplicate delivery | Repeated workflow ID rejected, including completed execution | Native `REJECT_DUPLICATE`; not a PostgreSQL outbox test |
| Cancel | In-flight activity observes cancellation, records stop, successor is not scheduled | Engine cancellation plus heartbeat/cooperative activity |
| Total deadline | Workflow execution timeout stops active activity and prevents successor | Native workflow execution timeout; retry/deadline combination not tested |
| Agent cancel | Paused second model request observes cancellation; second tool never executes | `TemporalDurability` model activity cancellation |

The independent ledger is separate from Temporal history, so a replay cannot
create a false “one call” result by reading its own cached assertion counter.
Model step 1 starts twice after a hard interruption because its first attempt
was not confirmed; model step 0 and tool 0 occur once. No exactly-once guarantee
is claimed for an external effect whose response was lost.

## Integration constraints and costs

Use `TemporalDurability` on a normal Agent, with
`DynamicToolset(factory, id="gateway")` passed when constructing it. In pinned
2.40.0, a plain custom `AbstractToolset` is not automatically temporalized, and
an `@agent.toolset` registration happens too late for durable activity binding.
The factory can return a generic gateway resolving tools from immutable deps;
new business tools need no per-plugin Python worker registration. This was
verified through installed source and the running probe. The
[official Temporal integration documentation](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/)
describes the activity boundaries and stable registration requirement.

The probe adds no persistence engine: Temporal owns workflow/activity state.
Platform launch transactions, projections, immutable definitions and effect
reconciliation remain application responsibilities. The gateway must keep
credentials out of serialized deps; this probe uses no credentials and therefore
does not prove secret redaction.

One server and one worker process sufficed locally. A single observed RSS sample
was 180592 KiB for the dev server and 102128 KiB for the worker, measured with
`ps -Ao pid,rss,command` during the final run. This is a point observation, not a
load benchmark. Server/worker operations, deterministic workflow code and
retaining/routing old core worker artifacts add operating responsibilities.

## Limits of this probe

The following boundaries were not established by this isolated experiment.
Current product implementation and its separate regression evidence are described
in the [architecture reference](../../../../docs/架构说明.md); this list is not a
claim that those boundaries remain unimplemented in the product.

- PostgreSQL atomic Run/snapshot/outbox save and interruption before dispatch.
- Actual old/new core worker artifact routing or worker versioning. Checking a
  fake core digest exists is not proof of replaying old executable code.
- Real MCP Streamable HTTP transport and independently deployed plugin images.
- Tool output schema rejection and unknown-effect query/deduplication.
- Retry attempts bounded by a shared total deadline.
- Temporal schedules, overlap/misfire/timezone handling.
- Full application domain contracts, immutable output store, UI and Compose.

Temporal is now the selected product engine, following the user decision recorded
in [STATUS](../../../../STATUS.md#已完成迭代). The three-candidate evidence and
its limits are consolidated in the [engine comparison](../../../../docs/执行引擎比较.md).
The native Pydantic AI call boundary and observed hard-restart behavior informed
that decision. Selection does not turn this probe into full A16 or A01–A18
acceptance; the actual Core/Worker/plugin integration requires its own evidence.

## Validation

All returned exit code 0 after the final code changes:

```bash
backend/.venv/bin/ruff check backend/experiments/engines/temporal
backend/.venv/bin/black --check backend/experiments/engines/temporal
backend/.venv/bin/isort --check-only backend/experiments/engines/temporal
/tmp/sd-temporal-probe-venv/bin/python backend/experiments/engines/temporal/probe.py
git diff --check
```

The probe is a cohesive integration scenario. Source responsibility guidance is
owned by the [source responsibility rules](../../../../docs/源代码规模与职责规则.md).
The experiment itself did not change public APIs, application data or the shared
runtime dependency manifest.
