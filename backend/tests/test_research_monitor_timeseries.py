"""Rolling observation dates retain series identity without erasing financial periods."""

from tests.test_research_monitor import monitor, scope

MonitorScope = monitor.MonitorScope
changes_since = monitor.changes_since


def point(day, value, *, official=False, vintage="2026-09-16"):
    from finance_plugin.research_evidence import ResearchEvidence

    return ResearchEvidence.model_validate(
        dict(
            evidenceId=f"{day}-{value}",
            sourceId="fred:CPI" if official else "yahoo:MSFT",
            kind="fact" if official else "observation",
            title="Observation",
            sourceType="official" if official else "market",
            metric="CPI" if official else "market.close",
            value=value,
            unit="USD",
            periodEnd=day,
            verified=True,
            retrievedAt="2026-09-17T00:00:00Z",
            availableByDate=vintage,
        )
    )


def test_latest_market_point_compares_across_rolling_dates():
    config = scope()
    config["rules"] = [
        dict(concept="market.close", unit="USD", direction="increase", absoluteChange="10")
    ]
    previous = [point("2026-09-14", "10"), point("2026-09-15", "100")]
    current = [point("2026-09-16", "120"), point("2026-09-15", "100")]
    changes = changes_since(MonitorScope.model_validate(config), current, previous)
    assert len(changes) == 1
    assert changes[0].kind == "metric_threshold"
    assert changes[0].evidence_id == "2026-09-16-120"
    assert changes[0].previous_evidence_id == "2026-09-15-100"
    current[0] = point("2026-09-16", "105")
    assert changes_since(MonitorScope.model_validate(config), current, previous) == []


def test_fred_new_period_revision_and_vintage_refresh():
    config = MonitorScope.model_validate(scope())
    previous = [point("2026-07-01", "100", official=True)]
    refreshed = [point("2026-07-01", "100", official=True, vintage="2026-09-17")]
    assert changes_since(config, refreshed, previous) == []
    updated = [point("2026-08-01", "100", official=True)]
    assert [c.kind for c in changes_since(config, updated, previous)] == ["new_disclosure"]
    revised = [point("2026-07-01", "101", official=True)]
    assert [c.kind for c in changes_since(config, revised, previous)] == ["fact_revision"]
