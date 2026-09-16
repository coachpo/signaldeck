"""Collection boundaries must survive provider projections and evidence merging."""

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

from finance_plugin.research_collection import (  # noqa: E402
    ResearchMergeInput,
    make_evidence,
    merge_evidence,
)
from finance_plugin.research_market import (  # noqa: E402
    ResearchMarketInput,
    collect_market_evidence,
)

NOW = datetime(2026, 9, 16, 15, tzinfo=UTC)


def item(**changes):
    values = dict(
        source_id="news-source",
        source_type="news",
        kind="excerpt",
        title="News",
        url="https://example.org/news",
        published_at=NOW - timedelta(days=1),
        retrieved_at=NOW,
        locator="summary",
        symbol="NVDA",
        verified=True,
    )
    values.update(changes)
    return make_evidence(**values)


class Market:
    def get_indicator_snapshot(self, symbol, **kwargs):
        return SimpleNamespace(provider="yahoo_finance", rows=[], warnings=[])

    def get_ohlcv_snapshot(self, symbols, **kwargs):
        def row(at):
            return SimpleNamespace(
                at=at,
                open=Decimal("10"),
                high=Decimal("12"),
                low=Decimal("9"),
                close=Decimal("11"),
                volume=Decimal("15"),
            )

        return SimpleNamespace(
            warnings=[],
            series=[
                SimpleNamespace(
                    symbol="NVDA",
                    provider="yahoo_finance",
                    currency="USD",
                    rows=[row(NOW - timedelta(days=1)), row(NOW), row(NOW + timedelta(days=1))],
                )
            ],
        )

    def get_news_snapshot(self, **kwargs):
        return SimpleNamespace(
            warnings=[],
            items=[
                SimpleNamespace(
                    title="Title",
                    url="https://example.org/story",
                    source="News source",
                    published_at=NOW - timedelta(hours=1),
                    summary="Excerpt",
                )
            ],
        )


class Social:
    def get_social_sentiment_snapshot(self, *args, **kwargs):
        raise RuntimeError("api_key=secret-must-not-leak")


def test_daily_close_never_uses_in_progress_or_future_bar():
    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", as_of_date=NOW.date()), Market(), Social(), now=NOW
    )
    market = [e for e in result.evidence if e.source_type == "market"]
    assert len(market) == 5
    assert {e.period_end.isoformat() for e in market} == {"2026-09-15"}
    assert all(e.publication_date and not e.published_at for e in market)
    assert [c.source_id for c in result.coverage] == ["market", "news"]
    assert next(e for e in result.evidence if e.source_type == "news").text == "Excerpt"


def test_optional_failure_does_not_remove_basic_evidence_or_expose_exception():
    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", as_of_date=NOW.date(), include_social=True),
        Market(),
        Social(),
        now=NOW,
    )
    assert len(result.evidence) == 6
    assert result.coverage[-1].complete is False
    assert "secret-must-not-leak" not in result.model_dump_json()
    assert any("Optional social" in gap for gap in result.gaps)


def test_stable_id_and_merge_ignore_retrieval_time():
    first = item()
    second = item(retrieved_at=NOW + timedelta(seconds=1))
    assert first.evidence_id == second.evidence_id
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA",
            as_of_date=NOW.date(),
            groups=[[first], [second]],
            upstream_gaps=["SEC unavailable"],
        ),
        now=NOW,
    )
    assert len(result.evidence) == 1
    assert result.gaps == ["SEC unavailable"]


def test_conflicting_id_excludes_both_and_cutoff_is_exclusive():
    first = item()
    conflict = first.model_copy(update={"text": "different"})
    future = item(published_at=NOW)
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA", as_of_date=NOW.date(), groups=[[first, conflict, future]]
        ),
        now=NOW,
    )
    assert result.evidence == []
    assert any("conflicting" in g for g in result.gaps)
    assert any("cutoff" in g for g in result.gaps)


def test_user_material_remains_unverified_and_date_precision_excludes_intraday():
    material = dict(
        category="新闻",
        title="Title",
        publishedDate="2026-09-15",
        source="https://example.org",
        content="Supplied content",
    )
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA", as_of_date=NOW.date(), groups=[], supportingMaterials=[material]
        ),
        now=NOW,
    )
    assert result.evidence[0].verified is False
    material["publishedDate"] = "2026-09-16"
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA", as_of_date=NOW.date(), groups=[], supportingMaterials=[material]
        ),
        now=NOW,
    )
    assert result.evidence == []


def test_cutoff_after_requested_day_rejected():
    with pytest.raises(ValueError, match="day boundary"):
        merge_evidence(
            ResearchMergeInput(symbol="NVDA", asOfDate="2026-09-14", cutoffAt=NOW, groups=[]),
            now=NOW,
        )


def test_social_samples_keep_publication_but_counts_are_retrieval_state():
    class SocialSamples:
        def get_social_sentiment_snapshot(self, *args, **kwargs):
            return SimpleNamespace(
                warnings=[],
                sources=["reddit"],
                source_blocks=[
                    SimpleNamespace(
                        source="reddit",
                        provider="reddit_rss",
                        title="Discussion",
                        summary="A hypothesis",
                        url="https://reddit.com/r/example/comments/123",
                        as_of=NOW - timedelta(days=1),
                        metrics=[SimpleNamespace(name="comments", value="24", unit="count")],
                    )
                ],
            )

    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", as_of_date=NOW.date(), include_social=True),
        Market(),
        SocialSamples(),
        now=NOW,
    )
    social = [item for item in result.evidence if item.source_type == "social"]
    assert len(social) == 1
    assert social[0].published_at == NOW - timedelta(days=1)
    assert social[0].value is None
    assert any("comments=24" in gap and "not cutoff" in gap for gap in result.gaps)
    assert any("Returned 1" in gap for gap in result.gaps)
    assert not result.coverage[-1].complete


def test_merge_removes_excluded_ids_from_coverage():
    from finance_plugin.research_monitor_contracts import Coverage

    future = item(published_at=NOW)
    coverage = Coverage(
        source_id="news", complete=True, observed_at=NOW, evidence_ids=[future.evidence_id]
    )
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA", as_of_date=NOW.date(), groups=[[future]], coverage_groups=[[coverage]]
        ),
        now=NOW,
    )
    assert result.coverage[0].evidence_ids == []
    assert not result.coverage[0].complete


@pytest.mark.parametrize(
    ("day", "cutoff"),
    [("2026-03-08", "2026-03-09T04:00:00+00:00"), ("2026-11-01", "2026-11-02T05:00:00+00:00")],
)
def test_collection_cutoff_follows_new_york_dst(day, cutoff):
    result = merge_evidence(
        ResearchMergeInput(symbol="NVDA", asOfDate=day, groups=[]),
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert result.cutoff_at.isoformat() == cutoff


def test_merge_preserves_failures_from_all_collection_nodes():
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA",
            asOfDate=NOW.date(),
            groups=[[item()]],
            gapGroups=[
                ["SEC unavailable"],
                ["Optional social collection failed"],
                ["SEC unavailable", "Official document body unavailable"],
            ],
        ),
        now=NOW,
    )
    assert result.gaps == [
        "SEC unavailable",
        "Optional social collection failed",
        "Official document body unavailable",
    ]
    assert len(result.evidence) == 1


def test_gap_overflow_is_bounded_and_explicit():
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA",
            asOfDate=NOW.date(),
            groups=[],
            gapGroups=[[f"failure {i}" for i in range(350)]],
        ),
        now=NOW,
    )
    assert len(result.gaps) == 300
    assert result.gaps[0] == "failure 0"
    assert "gap limit of 300 exceeded" in result.gaps[-1]


def valuation_inputs():
    from datetime import date

    from finance_plugin.research_monitor_contracts import Coverage

    market = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", asOfDate=NOW.date()),
        Market(),
        Social(),
        now=NOW,
    )
    shares = item(
        source_id="sec:filing",
        source_type="sec",
        kind="fact",
        metric="shares_outstanding",
        value="1000",
        unit="shares",
        period_end=date(2026, 8, 1),
        accession="filing",
    )
    return (
        market,
        shares,
        Coverage(
            source_id="sec", complete=True, observed_at=NOW, evidence_ids=[shares.evidence_id]
        ),
    )


def test_valuation_joins_market_and_financial_evidence_without_promoting_estimate():
    market, shares, sec_coverage = valuation_inputs()
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA",
            asOfDate=NOW.date(),
            includeValuation=True,
            groups=[market.evidence, [shares]],
            coverageGroups=[market.coverage, [sec_coverage]],
        ),
        now=NOW,
    )
    estimate = next(e for e in result.evidence if e.metric == "market_cap_estimate")
    assert estimate.value == "11000"
    assert not estimate.verified
    assert set(estimate.input_evidence_ids) <= {e.evidence_id for e in result.evidence}
    valuation = next(c for c in result.coverage if c.source_id == "valuation")
    assert not valuation.complete
    assert valuation.evidence_ids == [estimate.evidence_id]
    assert {key for c in result.coverage for key in c.evidence_ids} == {
        e.evidence_id for e in result.evidence
    }
    assert any("not a verified" in gap for gap in result.gaps)


def test_valuation_without_inputs_returns_gap_and_empty_explicit_coverage():
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA", asOfDate=NOW.date(), includeValuation=True, groups=[[item()]]
        ),
        now=NOW,
    )
    assert len(result.evidence) == 1
    assert result.coverage[0].source_id == "valuation"
    assert any("Valuation unavailable" in gap for gap in result.gaps)
    assert result.coverage[0].evidence_ids == []
    assert not result.coverage[0].complete


def test_estimates_follow_the_combined_evidence_limit_and_never_dangle_coverage():
    market, shares, sec_coverage = valuation_inputs()
    filler = [item(title=f"Fact {i}") for i in range(293)]
    result = merge_evidence(
        ResearchMergeInput(
            symbol="NVDA",
            asOfDate=NOW.date(),
            includeValuation=True,
            groups=[market.evidence, [shares], filler],
            coverageGroups=[market.coverage, [sec_coverage]],
        ),
        now=NOW,
    )
    assert len(result.evidence) == 300
    valuation = next(c for c in result.coverage if c.source_id == "valuation")
    assert valuation.evidence_ids == []
    assert any("Evidence truncated" in gap for gap in result.gaps)


@pytest.mark.parametrize(
    ("available", "cutoff", "eligible"),
    [
        ("2026-09-15", "2026-09-16T04:00:00Z", True),
        ("2026-09-15", "2026-09-16T03:59:59Z", False),
        ("2026-09-16", "2026-09-16T15:00:00Z", False),
        (None, "2026-09-16T15:00:00Z", False),
    ],
)
def test_explicit_vintage_upper_bound_never_becomes_publication_date(available, cutoff, eligible):
    from datetime import date

    macro = item(
        published_at=None,
        available_by_date=date.fromisoformat(available) if available else None,
        period_end=date(2026, 8, 1),
    )
    result = merge_evidence(
        ResearchMergeInput(symbol="NVDA", asOfDate=NOW.date(), cutoffAt=cutoff, groups=[[macro]]),
        now=NOW,
    )
    assert bool(result.evidence) is eligible
    if eligible:
        assert result.evidence[0].published_at is None
        assert result.evidence[0].publication_date is None
        assert result.evidence[0].available_by_date == date(2026, 9, 15)


def test_compact_context_bounds_preserves_values_and_source_diversity():
    from finance_plugin.research_context import context_size

    evidence = [
        item(
            title=f"SEC numeric {i}",
            source_type="sec",
            metric=f"metric_{i}",
            value="1234567890.123456789",
            unit="USD",
            text="Long excerpt " * 800,
        )
        for i in range(90)
    ]
    evidence += [
        item(title=source, source_type=source, text="Source excerpt")
        for source in ("official", "news", "social", "market", "prediction")
    ]
    result = merge_evidence(
        ResearchMergeInput(symbol="NVDA", asOfDate=NOW.date(), groups=[evidence]), now=NOW
    )
    assert result.analysis_context_truncated
    assert len(result.evidence) == 95
    assert len(result.analysis_evidence) <= 64
    assert context_size(result.analysis_evidence) <= 24000
    original = {e.evidence_id: e for e in evidence}
    assert {e.source_type for e in result.analysis_evidence} == {
        "sec",
        "official",
        "news",
        "social",
        "market",
        "prediction",
    }
    for compact in result.analysis_evidence:
        assert compact.value == original[compact.evidence_id].value
        assert compact.source_id == original[compact.evidence_id].source_id
        assert len(compact.text) <= 800
    assert any(e.excerpt_truncated for e in result.analysis_evidence)


def test_compact_context_excludes_superseded_but_retains_full_ledger():
    from finance_plugin.research_context import make_analysis_context

    old = item(title="Old", metric="revenue", value="1", unit="USD")
    current = item(
        title="Current",
        metric="revenue",
        value="2",
        unit="USD",
        supersedes_evidence_id=old.evidence_id,
    )
    unknown = item(title="Unverified", verified=False)
    evidence = [old, current, unknown]
    compact = make_analysis_context(evidence)
    assert [e.evidence_id for e in compact] == [current.evidence_id, unknown.evidence_id]
    assert compact[-1].verified is False
    result = merge_evidence(
        ResearchMergeInput(symbol="NVDA", asOfDate=NOW.date(), groups=[evidence]), now=NOW
    )
    assert len(result.evidence) == 3
    assert result.analysis_context_truncated


def test_compact_context_is_stable_across_provider_result_order():
    from finance_plugin.research_context import make_analysis_context

    evidence = [item(title=f"Sample {i}", source_type="news") for i in range(20)]
    first = make_analysis_context(evidence)
    second = make_analysis_context(list(reversed(evidence)))
    assert first == second
    assert len(first) == 6


class IndicatorMarket(Market):
    def get_indicator_snapshot(self, symbol, **kwargs):
        self.indicator_call = (symbol, kwargs)
        values = [
            SimpleNamespace(
                name="sma_20", value=Decimal("10.123456789012345678"), null_reason=None
            ),
            SimpleNamespace(name="rsi_14", value=Decimal("55.55555555"), null_reason=None),
        ]
        return SimpleNamespace(
            provider="yahoo_finance",
            warnings=[],
            rows=[
                SimpleNamespace(at=NOW - timedelta(days=1), values=values),
                SimpleNamespace(
                    at=NOW, values=[SimpleNamespace(name="rsi_14", value=Decimal("99"))]
                ),
            ],
        )


def test_indicators_preserve_original_bounded_service_call_values_and_source():
    market = IndicatorMarket()
    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", asOfDate=NOW.date()), market, Social(), now=NOW
    )
    symbol, args = market.indicator_call
    assert symbol == "NVDA"
    assert args["start_date"] == NOW - timedelta(days=90)
    assert args["end_date"] == args["current_date"] == NOW
    assert args["row_limit"] == 30
    assert [(s.indicator, s.window) for s in args["indicators"]] == [("sma", 20), ("rsi", 14)]
    by_metric = {e.metric: e for e in result.evidence}
    sma, rsi, close = [
        by_metric[name] for name in ("market.sma_20", "market.rsi_14", "market.close")
    ]
    assert sma.value == "10.123456789012345678"
    assert rsi.value == "55.55555555"
    assert sma.currency == sma.unit == close.currency == "USD"
    assert rsi.currency is None and rsi.unit == "points"
    assert sma.source_id == rsi.source_id == close.source_id
    assert sma.publication_date == rsi.publication_date == close.publication_date
    assert sma.published_at is None
    assert {sma.evidence_id, rsi.evidence_id} <= set(result.coverage[0].evidence_ids)


def test_indicator_warmup_or_failure_retains_prices_and_explicit_gap():
    class Warmup(IndicatorMarket):
        def get_indicator_snapshot(self, symbol, **kwargs):
            result = super().get_indicator_snapshot(symbol, **kwargs)
            result.rows[0].values[0].value = None
            result.rows[0].values[0].null_reason = "insufficient_history"
            return result

    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", asOfDate=NOW.date()), Warmup(), Social(), now=NOW
    )
    assert any(e.metric == "market.close" for e in result.evidence)
    assert any(e.metric == "market.rsi_14" for e in result.evidence)
    assert not any(e.metric == "market.sma_20" for e in result.evidence)
    assert any("sma_20" in g and "insufficient_history" in g for g in result.gaps)

    class Failed(Market):
        def get_indicator_snapshot(self, symbol, **kwargs):
            raise RuntimeError("secret=do-not-echo")

    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", asOfDate=NOW.date()), Failed(), Social(), now=NOW
    )
    assert any(e.metric == "market.close" for e in result.evidence)
    assert any("indicator collection failed" in g for g in result.gaps)
    assert "do-not-echo" not in result.model_dump_json()


@pytest.mark.parametrize("currency", ["EUR", None])
def test_indicator_currency_comes_from_price_source(currency):
    class CurrencyMarket(IndicatorMarket):
        def get_ohlcv_snapshot(self, symbols, **kwargs):
            result = super().get_ohlcv_snapshot(symbols, **kwargs)
            result.series[0].currency = currency
            return result

    result = collect_market_evidence(
        ResearchMarketInput(symbol="NVDA", asOfDate=NOW.date()),
        CurrencyMarket(),
        Social(),
        now=NOW,
    )
    indicators = [e for e in result.evidence if e.metric in {"market.sma_20", "market.rsi_14"}]
    if currency:
        sma = next(e for e in indicators if e.metric == "market.sma_20")
        assert sma.currency == sma.unit == currency
    else:
        assert indicators == []
        assert any("currency source" in gap for gap in result.gaps)
    assert not any(e.currency == "USD" for e in result.evidence)
