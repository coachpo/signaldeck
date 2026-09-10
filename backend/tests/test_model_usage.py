"""Usage reads count logical calls once and preserve missing billing coverage."""

from datetime import UTC, date, datetime, timedelta

from app.application.model_usage import ModelCallUsage, summarize_model_calls
from app.domain.execution import ExecutionEvidence
from app.infrastructure.model_usage import day_window, read_model_usage
from tests.test_task_experience import configured
from tests.test_task_experience import platform as platform_fixture

platform = platform_fixture


def launch(client, launch_id):
    return client.post(
        "/api/workflow-packages/api-package/launches",
        json={"workflowKey": "main", "parameters": {"text": "hello"}, "launchId": launch_id},
    ).json()["id"]


def record_call(
    store,
    run_id,
    call_id,
    started_at,
    *,
    status="succeeded",
    usage=None,
    output=None,
    attempts=("succeeded",),
    earliest=None,
):
    node, agent = f"{call_id}:node", f"{call_id}:agent"
    store.record_evidence_batch(
        [
            ExecutionEvidence(
                id=node, run_id=run_id, node_id="echo", kind="node", status="running"
            ),
            ExecutionEvidence(
                id=agent,
                run_id=run_id,
                node_id="echo",
                parent_id=node,
                kind="agent",
                status="running",
            ),
            ExecutionEvidence(
                id=call_id,
                run_id=run_id,
                node_id="echo",
                parent_id=agent,
                kind="model",
                status=status,
                started_at=started_at,
                finished_at=started_at + timedelta(seconds=2) if status != "running" else None,
                metadata={"usage": usage} if usage is not None else {},
                output=output,
            ),
            *[
                ExecutionEvidence(
                    id=f"{call_id}:attempt:{i}",
                    run_id=run_id,
                    node_id="echo",
                    parent_id=call_id,
                    kind="attempt",
                    status=attempt_status,
                    started_at=earliest if i == 0 and earliest else started_at,
                    finished_at=started_at + timedelta(seconds=2),
                    metadata={"networkKind": "model_request"},
                    output=output,
                )
                for i, attempt_status in enumerate(attempts)
            ],
        ]
    )


def test_retry_and_duplicate_usage_references_are_not_double_counted(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    run_id = launch(client, "usage-retry")
    stamp = datetime(2026, 9, 10, 10, tzinfo=UTC)
    record_call(
        store,
        run_id,
        "call",
        stamp,
        usage={"inputTokens": 10, "outputTokens": 4},
        attempts=("failed", "unknown", "succeeded"),
        earliest=stamp - timedelta(seconds=3),
    )
    record_call(store, run_id, "pending", stamp, status="running", attempts=("running",))
    first = read_model_usage(store, run_id=run_id)
    second = read_model_usage(store, run_id=run_id)
    assert first.summary == second.summary
    assert first.summary.model_calls == 2
    assert first.summary.input_tokens == 10 and first.summary.output_tokens == 4
    assert first.summary.confirmed_calls == 1 and first.summary.unconfirmed_calls == 1
    assert first.summary.network_attempts == 4
    assert first.summary.failed_network_attempts == 1
    assert first.summary.unconfirmed_network_attempts == 2
    assert first.summary.usage_missing_calls == 1 and first.summary.usage_coverage == "partial"
    assert first.summary.duration_ms == 5000
    assert first.models[0].model_id == "controlled"


def test_failed_and_missing_old_usage_are_unknown_but_explicit_zero_is_known(
    platform,
):
    client, store, artifacts = platform
    configured(client, store, model=True)
    run_id = launch(client, "usage-missing")
    stamp = datetime.now(UTC)
    record_call(store, run_id, "failed", stamp, status="failed", attempts=("failed",))
    # These are the SDK's historical defaults when the provider omitted usage.
    record_call(
        store, run_id, "old-zero", stamp, output={"usage": {"input_tokens": 0, "output_tokens": 0}}
    )
    read = read_model_usage(store, run_id=run_id)
    assert read.summary.input_tokens is None and read.summary.output_tokens is None
    assert read.summary.usage_coverage == "none"
    record_call(store, run_id, "zero", stamp, usage={"inputTokens": 0, "outputTokens": 0})
    read = read_model_usage(store, run_id=run_id)
    assert read.summary.input_tokens == 0 and read.summary.output_tokens == 0
    assert read.summary.usage_known_calls == 1 and read.summary.usage_missing_calls == 2
    # The same content reference is still two distinct real calls, not one cache hit.
    payload = {"usage": {"input_tokens": 7, "output_tokens": 2}, "parts": [{"content": "x" * 5000}]}
    record_call(store, run_id, "old-positive", stamp, output=payload)
    read = read_model_usage(store, run_id=run_id)
    assert read.summary.input_tokens == 7 and read.summary.output_tokens == 2
    assert artifacts is not None


def test_local_day_boundary_and_retried_call_start_survive_dst(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    run_id = launch(client, "usage-day")
    start, end = day_window(date(2026, 3, 29), "Europe/Helsinki")
    assert (end - start).total_seconds() == 23 * 3600
    record_call(
        store,
        run_id,
        "before",
        start - timedelta(seconds=1),
        usage={"inputTokens": 100, "outputTokens": 100},
    )
    record_call(
        store,
        run_id,
        "at-boundary",
        start + timedelta(microseconds=1),
        usage={"inputTokens": 3, "outputTokens": 2},
    )
    record_call(store, run_id, "at-end", end, usage={"inputTokens": 100, "outputTokens": 100})
    record_call(
        store,
        run_id,
        "retry-crossing",
        start + timedelta(seconds=10),
        earliest=start - timedelta(seconds=10),
        attempts=("failed", "succeeded"),
        usage={"inputTokens": 100, "outputTokens": 100},
    )
    read = read_model_usage(store, day=date(2026, 3, 29), timezone="Europe/Helsinki")
    assert read.summary.model_calls == 1
    assert read.summary.input_tokens == 3 and read.summary.output_tokens == 2
    assert read.window_start == start and read.window_end == end
    previous = read_model_usage(store, day=date(2026, 3, 28), timezone="Europe/Helsinki")
    assert previous.summary.model_calls == 2
    assert previous.summary.input_tokens == 200


def test_breakdown_uses_frozen_models_and_api_reads_do_not_resolve_credentials(
    platform, monkeypatch
):
    client, store, _ = platform
    configured(client, store, model=True)
    first = launch(client, "usage-original")
    store.save_resource(
        "local-model", "model", {"baseUrl": "http://127.0.0.1:1", "modelId": "second-model"}
    )
    second = launch(client, "usage-current")
    stamp = datetime(2026, 9, 10, 10, tzinfo=UTC)
    for i, run_id in enumerate([first, second]):
        record_call(store, run_id, f"call-{i}", stamp, usage={"inputTokens": 3, "outputTokens": 2})

    def forbidden(*args):
        raise AssertionError("Usage reads cannot resolve credentials")

    monkeypatch.setattr(store, "resolve_credentials", forbidden)
    monkeypatch.setattr(store, "resolve_bound_credentials", forbidden)
    read = client.get("/api/model-usage", params={"date": "2026-09-10", "timezone": "UTC"})
    assert read.status_code == 200, read.text
    assert read.json()["summary"]["inputTokens"] == 6
    assert {model["modelId"] for model in read.json()["models"]} == {"controlled", "second-model"}
    assert client.get(f"/api/runs/{first}/usage").json()["summary"]["modelCalls"] == 1
    assert (
        client.get(
            "/api/model-usage", params={"date": "2026-09-10", "timezone": "made/up"}
        ).status_code
        == 422
    )
    assert client.get("/api/runs/missing/usage").status_code == 404


def test_logical_identity_deduplication_and_empty_scope():
    call = ModelCallUsage(
        "one",
        "model",
        "model",
        "responses",
        datetime.now(UTC),
        "succeeded",
        2,
        3,
        100,
        ("succeeded",),
    )
    assert summarize_model_calls([call, call]).input_tokens == 2
    assert summarize_model_calls([call, call]).network_attempts == 1
    empty = summarize_model_calls([])
    assert empty.input_tokens == 0 and empty.output_tokens == 0
    assert empty.usage_coverage == "complete"
