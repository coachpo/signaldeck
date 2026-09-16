"""Prediction state changes must never be mistaken for comparable price changes."""

from tests import test_research_monitor as support
from tests.test_research_monitor import begin, call, observation, scope

runtime = support.runtime


def test_prediction_rule_change_closure_and_unverified_metadata(runtime):
    config = scope()
    config["rules"] = [dict(concept="revenue", unit="USD", direction="either", absoluteChange="1")]
    first = begin(runtime, config)
    payload = observation(first, "50", kind="prediction")
    meta = dict(
        venue="kalshi",
        eventId="event",
        contractId="contract",
        outcome="yes",
        ruleVersion="v1",
        status="open",
        quoteType="bid_ask",
    )
    payload["evidence"][0]["prediction"] = meta
    call(runtime, "monitor_observe", payload)
    second = begin(runtime, config)
    payload = observation(second, "70", kind="prediction")
    payload["evidence"][0]["prediction"] = {**meta, "ruleVersion": "v2"}
    result = call(runtime, "monitor_observe", payload)
    assert [c["kind"] for c in result["changes"]] == ["contract_changed"]
    third = begin(runtime, config)
    payload = observation(third, "100", kind="prediction")
    payload["evidence"][0]["prediction"] = {**meta, "ruleVersion": "v2", "status": "closed"}
    result = call(runtime, "monitor_observe", payload)
    assert [c["kind"] for c in result["changes"]] == ["contract_closed"]
    fourth = begin(runtime, config)
    payload = observation(fourth, kind="prediction")
    payload["evidence"][0]["prediction"] = {**meta, "ruleVersion": "v3", "status": "closed"}
    payload["evidence"][0]["verified"] = False
    result = call(runtime, "monitor_observe", payload)
    assert result["state"] == "invalid"
    assert "contract_changed_unverified:e-filing-1" in result["warnings"]


def test_unchanged_deadline_crossing_is_reported_as_expiry():
    from datetime import UTC, datetime, timedelta

    from finance_plugin.research_evidence import ResearchEvidence
    from finance_plugin.research_monitor_prediction import prediction_changes

    now = datetime.now(UTC)
    evidence = ResearchEvidence.model_validate(
        dict(
            evidenceId="e",
            sourceId="s",
            kind="observation",
            title="Contract",
            retrievedAt=now.isoformat(),
            publishedAt=(now - timedelta(hours=2)).isoformat(),
            verified=True,
            prediction=dict(
                venue="kalshi",
                eventId="event",
                contractId="c",
                outcome="yes",
                ruleVersion="v1",
                status="open",
                deadline=(now - timedelta(hours=1)).isoformat(),
            ),
        )
    )
    changes, warnings = prediction_changes([evidence], [evidence], now, now - timedelta(hours=2))
    assert [change.kind for change in changes] == ["contract_closed"]
    assert warnings == []
