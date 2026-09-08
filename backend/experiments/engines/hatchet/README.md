# Hatchet candidate integration probe

This is an isolated T06/A16 experiment against frozen target
`bca05dcd666e96561426224b89b0e06aed186a22`. It imports no SignalDeck application
code and does not establish platform acceptance.

The implementation fixes Hatchet engine/embedded sidecar `v0.105.16`, Python SDK
`1.40.0`, Pydantic AI slim `2.40.0`, and Python `3.13.13`. Transitive Python
versions are in `requirements.lock`. These were checked against the official
release API and PyPI on 2026-09-08. The observed Darwin ARM64 sidecar SHA-256 was
`d649c05fe45609db2c40470c1e5b2c824b714e88189065122c693301c05282a6`.
The SDK verifies the downloaded sidecar against its release checksum.

Run from the repository root:

```bash
backend/experiments/engines/hatchet/run.sh
```

For occupied default ports:

```bash
SD_HATCHET_GRPC_PORT=17080 SD_HATCHET_API_PORT=28250 \
  backend/experiments/engines/hatchet/run.sh
```

The script creates a uniquely owned directory under `/tmp`, installs the locked
SDK, starts a real Hatchet engine and its bundled PostgreSQL, and starts separate
call and durable workers. No Docker, account, hosted model, application database,
or real business credential is needed. The engine persists independently of the
fault-injected durable worker. The temporary engine token is kept in a mode-0600
file and removed at shutdown. Engine and worker processes stop after execution;
evidence, the isolated PostgreSQL directory and venv remain under the printed
path for inspection. They can be removed after reviewing the results.

`report.json` reports individual outcomes. An exit code of zero means the probe
completed its observations and its positive assertions passed; **inspect the
report for negative findings**, especially parent-child cancellation. It does not
mean all target criteria passed. `events.jsonl` contains fake-call timestamps and
counts; worker logs show attempts. No platform or external tracing service is
needed to read these probe files.

## Reproduction evidence

The complete launcher was executed with ports 17080/28250 and exited **0** on
2026-09-08. Evidence directory: `/tmp/signaldeck-hatchet.5GKgla`; launcher log:
`/tmp/signaldeck-hatchet-repro.log`. The report records the parent cancellation
failure separately. The original independent-engine run also exited 0, with
evidence in `/tmp/signaldeck-hatchet-evidence-final`. Both engines and all owned
workers were confirmed stopped; client token files were removed.

`ruff check`, `black --check`, `isort --check-only` over this candidate directory
and `git diff --check` passed. Each Python file is under 240 physical lines; the
long continuous runner is a fault-injection integration scenario.

## Evidence obtained

The executed scenario is A → (B, C) → D, with B → E to detect a global barrier.
The second scenario uses Pydantic AI with a model call, a tool call and a second
model call; two concurrent Runs have different frozen schemas and qualified tool
names. The recovery test kills the complete durable worker process group after
model-0 and tool results were confirmed, while model-1 is held at a gate. A fresh
worker resumes the same durable execution and the confirmed calls occur once.

| Observation | Actual result | Ownership and limits |
| --- | --- | --- |
| Parallel B/C and E before C ends | Passed | Hatchet durable child scheduling; code expresses the dependency graph. |
| Dynamic schema and qualified tool identities, concurrent Runs | Passed | Pydantic AI plus a custom per-Run model/tool child-task adapter. |
| Worker SIGKILL after confirmed model/tool | Passed, recovery attempt 2 | Hatchet checkpoint replay; observed reassignment took about 29 seconds. The call worker and engine remained alive. |
| New Run fresh tool result | Passed | No cross-Run cache configured; `fresh` marker differs. |
| Duplicate trigger | `IdempotencyCollisionError`, one A execution | Native 24-hour TTL dedup only. This is not a PostgreSQL transactional outbox or permanent Run identity test. |
| Direct active child cancellation | Passed, `CancelledError` observed | Native task cancellation, no completed tool effect. |
| Cancel durable parent with active child | **Failed within 8-second observation** | Parent cancellation did not stop the model child; releasing its gate let it finish. Default spawning requires further propagation integration. |
| Missing pinned artifact | Rejected on all task attempts | Probe file-existence guard only; real core/plugin artifact loading and upgrade recovery are untested. |
| Already expired deadline | Rejected on all task attempts | Explicit boundary guard only; total lifetime across waiting, active calls and retries is untested. |

`Tool.from_schema` passes schema to the model but intentionally skips built-in
argument validation. The probe explicitly applies `Draft202012Validator` at the
gateway. That validation is required adapter work, not an engine guarantee.
The in-process fake tool boundary does not validate MCP Streamable HTTP.

## Adaptation and operation costs

Hatchet provides durable child checkpoints, retry attempts, event history,
parallel child scheduling and task cancellation. Pydantic AI requests and tool
calls in this probe are converted into durable child tasks through a custom
`Model.request` implementation and schema-backed tool callbacks. The official
Pydantic AI distribution installed for this experiment does not contain a
Hatchet adapter; maintaining this integration belongs to SignalDeck if selected.

The embedded engine is convenient for an actual local comparison: one sidecar
plus PostgreSQL, two worker parent processes and SDK subprocesses. A spot RSS
sample observed approximately 89 MiB for the engine alone; this excludes
PostgreSQL, both Python workers and their children and is not a benchmark.
Deployment packaging would still need the target Compose topology. The
single-process Lite image is another official development/low-volume option.

Hatchet remains a viable durable candidate, but these results do not justify
preferring it over a combination with verified official Pydantic AI durability:
parent cancellation needs additional propagation work, permanent launch identity
needs more than finite native dedup, and core/plugin artifact routing is not yet
proved. These are concrete implementation costs, not evidence of impossibility.

Unverified: atomic platform outbox, indefinite Run identity, complete deadline
semantics, core/plugin upgrade and missing-artifact recovery, MCP transport,
unknown external-write reconciliation, timezone/overlap/misfire scheduling,
independent tool limiters, immutable content-addressed outputs, crash of every
worker simultaneously, and full platform evidence projections.

## Official sources

- [Engine release](https://github.com/hatchet-dev/hatchet/releases/tag/v0.105.16)
- [Embedded engine](https://docs.hatchet.run/v1/embedded)
- [Durable task constraints](https://docs.hatchet.run/v1/durable-tasks)
- [Child spawning](https://docs.hatchet.run/v1/child-spawning)
- [Idempotency strategies](https://docs.hatchet.run/v1/idempotency)
- [Python SDK release](https://pypi.org/project/hatchet-sdk/1.40.0/)
- [Pydantic AI release](https://pypi.org/project/pydantic-ai-slim/2.40.0/)
