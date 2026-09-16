"""Explicit research observations use the plugin's real PostgreSQL transaction journal."""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

for path in ("finance", "runtime"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / path))

from finance_plugin import research_monitor as monitor  # noqa: E402
from finance_plugin.models.base import Base  # noqa: E402
from finance_plugin.models.report import Report  # noqa: E402
from finance_plugin.models.research_monitor import ResearchHead, ResearchSnapshot  # noqa: E402
from plugin_runtime.operations import Journal, OperationBase  # noqa: E402


@pytest.fixture
def runtime(database_url):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    OperationBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    yield Journal(sessions), sessions
    engine.dispose()


def scope():
    return dict(
        symbol="MSFT",
        cik="0000789019",
        question="Cash generation",
        horizonMonths=3,
        ruleVersion="1",
        sources=[dict(sourceId="sec", required=True, maxAgeSeconds=3600)],
        rules=[],
    )


def call(runtime, name, args, operation=None):
    return monitor.execute(
        name, args, dict(runId="run", operationId=operation or str(uuid4())), runtime[0]
    )


def begin(runtime, config=None, operation=None):
    return call(
        runtime, "monitor_begin", dict(monitorKey="test", scope=config or scope()), operation
    )


def observation(snapshot, value="100", source="filing-1", kind="sec"):
    now = datetime.fromisoformat(snapshot["cutoffAt"])
    evidence = dict(
        evidenceId="e-" + source,
        sourceId=source,
        kind="fact",
        title="Revenue",
        retrievedAt=now.isoformat(),
        publishedAt=(now - timedelta(days=1)).isoformat(),
        verified=True,
        sourceType=kind,
        symbol="MSFT",
        metric="revenue",
        value=value,
        unit="USD",
    )
    return dict(
        snapshotId=snapshot["snapshotId"],
        evidence=[evidence],
        coverage=[
            dict(
                sourceId="sec",
                complete=True,
                observedAt=now.isoformat(),
                evidenceIds=[evidence["evidenceId"]],
            )
        ],
    )


def test_freeze_replay_and_scope_stability(runtime):
    op = str(uuid4())
    first = begin(runtime, operation=op)
    assert begin(runtime, operation=op) == first
    second = begin(runtime)
    assert second["snapshotId"] != first["snapshotId"]
    assert second["scopeHash"] == first["scopeHash"]
    assert second["cutoffAt"] > first["cutoffAt"]
    assert call(runtime, "monitor_observe", observation(first))["state"] == "no_baseline"
    result = call(runtime, "monitor_observe", observation(second))
    assert result["state"] == "unchanged" and not result["shouldResearch"]
    assert result["previousSnapshotId"] == first["snapshotId"]


def test_changes_invalid_and_scope_reset(runtime):
    first = begin(runtime)
    call(runtime, "monitor_observe", observation(first))
    invalid = begin(runtime)
    payload = observation(invalid)
    payload["coverage"][0]["complete"] = False
    assert call(runtime, "monitor_observe", payload)["state"] == "invalid"
    changed = begin(runtime)
    result = call(runtime, "monitor_observe", observation(changed, value="110", source="filing-2"))
    assert result["state"] == "changed" and result["shouldResearch"]
    assert result["previousSnapshotId"] == first["snapshotId"]
    assert {c["kind"] for c in result["changes"]} == {"new_disclosure", "fact_revision"}
    config = scope()
    config["ruleVersion"] = "2"
    reset = begin(runtime, config)
    assert call(runtime, "monitor_observe", observation(reset))["state"] == "no_baseline"


def test_rollback_does_not_freeze_or_save_snapshot(runtime, monkeypatch):
    original = monitor._begin

    def fail(session, payload, invocation):
        original(session, payload, invocation)
        raise RuntimeError("rollback")

    op = str(uuid4())
    monkeypatch.setattr(monitor, "_begin", fail)
    with pytest.raises(RuntimeError):
        begin(runtime, operation=op)
    assert runtime[0].query(op)["status"] == "not_found"
    with runtime[1]() as session:
        assert session.scalar(select(ResearchSnapshot)) is None
    monkeypatch.setattr(monitor, "_begin", original)
    saved = begin(runtime, operation=op)
    assert runtime[0].query(op)["output"] == saved


def test_concurrent_replay_and_old_completion_cannot_regress_head(runtime):
    op = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: begin(runtime, operation=op), range(4)))
    assert all(r == results[0] for r in results)
    older = results[0]
    newer = begin(runtime)
    call(runtime, "monitor_observe", observation(newer))
    call(runtime, "monitor_observe", observation(older))
    with runtime[1]() as session:
        head = session.scalar(select(ResearchHead))
        assert head.snapshot_id == newer["snapshotId"]


def test_report_outcome_separate_from_valid_observation(runtime):
    first = begin(runtime)
    call(runtime, "monitor_observe", observation(first))
    assert (
        call(
            runtime, "monitor_report_attach", dict(snapshotId=first["snapshotId"], status="failed")
        )["reportStatus"]
        == "failed"
    )
    second = begin(runtime)
    result = call(runtime, "monitor_observe", observation(second))
    assert result["state"] == "unchanged"
    third = begin(runtime)
    call(runtime, "monitor_observe", observation(third, "200"))
    with runtime[1].begin() as session:
        report = Report(
            name="test",
            slug="test",
            source="agent",
            content="report",
            metadata_={"createdBy": {"runId": "run"}, "researchSnapshotId": first["snapshotId"]},
        )
        session.add(report)
        session.flush()
        report_id = report.id
    args = dict(snapshotId=third["snapshotId"], status="succeeded", reportId=report_id)
    with pytest.raises(ValueError, match="snapshot_mismatch"):
        call(runtime, "monitor_report_attach", args)
    with runtime[1].begin() as session:
        session.get(Report, report_id).metadata_ = {
            "createdBy": {"runId": "run"},
            "researchSnapshotId": third["snapshotId"],
        }
    assert call(runtime, "monitor_report_attach", args)["reportId"] == report_id


def test_explicit_metric_threshold(runtime):
    config = scope()
    config["rules"] = [
        dict(concept="revenue", unit="USD", direction="increase", absoluteChange="10")
    ]
    first = begin(runtime, config)
    call(runtime, "monitor_observe", observation(first, kind="market"))
    second = begin(runtime, config)
    assert (
        call(runtime, "monitor_observe", observation(second, "105", kind="market"))["state"]
        == "unchanged"
    )
    third = begin(runtime, config)
    result = call(runtime, "monitor_observe", observation(third, "120", kind="market"))
    assert result["state"] == "changed"
    assert result["changes"][0]["kind"] == "metric_threshold"


def test_optional_failure_and_stale_required_evidence(runtime):
    config = scope()
    config["sources"].append(dict(sourceId="social", required=False, maxAgeSeconds=300))
    snapshot = begin(runtime, config)
    result = call(runtime, "monitor_observe", observation(snapshot))
    assert result["state"] == "no_baseline"
    assert "optional_source_invalid:social" in result["warnings"]
    stale = begin(runtime, config)
    payload = observation(stale)
    payload["evidence"][0]["retrievedAt"] = (
        datetime.fromisoformat(stale["cutoffAt"]) - timedelta(hours=2)
    ).isoformat()
    assert call(runtime, "monitor_observe", payload)["state"] == "invalid"


def test_retrieval_order_and_evidence_id_changes_are_not_material(runtime):
    first = begin(runtime)
    payload = observation(first)
    call(runtime, "monitor_observe", payload)
    second = begin(runtime)
    payload = observation(second)
    payload["evidence"][0]["evidenceId"] = "new-fetch-id"
    payload["evidence"][0]["title"] = "Changed model wording"
    payload["coverage"][0]["evidenceIds"] = ["new-fetch-id"]
    assert call(runtime, "monitor_observe", payload)["state"] == "unchanged"


def test_commit_response_loss_replays_original_observation(runtime):
    snapshot = begin(runtime)
    args = observation(snapshot)
    op = str(uuid4())
    saved = call(runtime, "monitor_observe", args, op)
    # A caller which lost the HTTP response reconciles the committed journal result.
    assert runtime[0].query(op)["output"] == saved
    assert call(runtime, "monitor_observe", args, op) == saved
    args["evidence"][0]["value"] = "999"
    with pytest.raises(ValueError, match="operation_input_conflict"):
        call(runtime, "monitor_observe", args, op)


def test_monitor_publishes_closed_supported_contracts():
    from app.domain.tool_contracts import ToolDefinition

    for definition in monitor.definitions():
        ToolDefinition.model_validate(definition)


def test_reordering_revisions_preserves_comparison(runtime):
    from copy import deepcopy

    first = begin(runtime)
    payload = observation(first)
    amended = deepcopy(payload["evidence"][0])
    amended.update(
        evidenceId="amended",
        sourceId="filing-2",
        value="110",
        publishedAt=(datetime.fromisoformat(first["cutoffAt"]) - timedelta(hours=12)).isoformat(),
    )
    payload["evidence"].append(amended)
    payload["coverage"][0]["evidenceIds"].append("amended")
    call(runtime, "monitor_observe", payload)
    second = begin(runtime)
    payload["snapshotId"] = second["snapshotId"]
    payload["evidence"].reverse()
    assert call(runtime, "monitor_observe", payload)["state"] == "unchanged"


def test_source_configuration_changes_reset_scope_but_order_does_not(runtime):
    config = scope()
    config.update(
        sourceUrls=["https://example.org/a", "https://example.org/b"],
        includePrediction=True,
        events=[
            dict(venue="kalshi", eventId="A", hypothesis="demand", reason="exposure"),
            dict(venue="kalshi", contractId="B", hypothesis="supply", reason="exposure"),
        ],
    )
    original = begin(runtime, config)
    config["sourceUrls"].reverse()
    config["events"].reverse()
    assert begin(runtime, config)["scopeHash"] == original["scopeHash"]
    config["includeSocial"] = True
    assert begin(runtime, config)["scopeHash"] != original["scopeHash"]
    config["events"] = []
    with pytest.raises(ValueError, match="prediction_events_required"):
        begin(runtime, config)
