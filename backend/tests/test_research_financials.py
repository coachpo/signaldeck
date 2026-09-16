# ruff: noqa: E402
"""SEC point-in-time facts use actual fiscal durations and traceable arithmetic."""

import sys
from datetime import UTC, date, datetime
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

import httpx
import pytest
from finance_plugin.research_financials import lookup_financials
from finance_plugin.research_financials_calculations import calculate_financials
from finance_plugin.research_financials_sec import (
    SecFinancialsProvider,
    parse_facts,
    period_type,
    research_cutoff,
)
from finance_plugin.runtime_market_data import parse_fundamentals_lookup_arguments


def row(
    value=100,
    *,
    start="2024-07-01",
    end="2025-06-30",
    filed="2025-07-30",
    acc="0000000001-25-000001",
    **extra,
):
    return {
        "val": value,
        "start": start,
        "end": end,
        "filed": filed,
        "accn": acc,
        "form": "10-K",
        "fy": 2025,
        "fp": "FY",
        **extra,
    }


def company(tags):
    return {"cik": 1, "facts": {"us-gaap": {tag: {"units": units} for tag, units in tags.items()}}}


def parse(tags, cutoff=datetime(2026, 1, 1, tzinfo=UTC), filings=None):
    return parse_facts(company(tags), filings or {}, cutoff)[0]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2024-07-01", "2025-06-30", "annual"),
        ("2023-01-30", "2024-01-28", "annual"),
        ("2023-01-23", "2024-01-28", "annual"),
        ("2024-07-01", "2024-09-30", "quarterly"),
        ("2024-01-29", "2024-07-28", "year_to_date"),
        (None, "2024-07-28", "instant"),
    ],
)
def test_actual_period_not_filing_fiscal_focus(start, end, expected):
    assert (
        period_type(date.fromisoformat(start) if start else None, date.fromisoformat(end))
        == expected
    )


def test_cutoff_handles_dst_and_freezes_present():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert research_cutoff(date(2025, 3, 9), now).isoformat() == "2025-03-10T04:00:00+00:00"
    assert research_cutoff(date(2025, 11, 2), now).isoformat() == "2025-11-03T05:00:00+00:00"
    assert research_cutoff(date(2026, 12, 1), now) == now


def test_revision_respects_publication_not_period_end():
    original = row(100)
    revised = row(110, filed="2025-08-10", acc="0000000001-25-000002")
    tags = {"Revenues": {"USD": [original, revised]}}
    before = parse(tags, datetime(2025, 8, 1, tzinfo=UTC))
    assert [f.value for f in before] == ["100"]
    after = parse(tags)
    assert [f.value for f in after if f.selected] == ["110"]
    assert after[1].supersedes_evidence_ids == [after[0].evidence_id]


def test_acceptance_timestamp_and_date_only_are_not_interchangeable():
    r = row(filed="2025-07-30")
    tags = {"Revenues": {"USD": [r]}}
    cutoff = datetime(2025, 7, 30, 15, tzinfo=UTC)
    assert parse(tags, cutoff) == []
    index = {r["accn"]: {"acceptanceDateTime": "2025-07-30T14:00:00Z"}}
    assert len(parse(tags, cutoff, index)) == 1
    index[r["accn"]]["acceptanceDateTime"] = "2025-07-30T15:00:00Z"
    assert parse(tags, cutoff, index) == []


def test_unsupported_currency_never_used_or_coerced():
    facts = parse({"Revenues": {"EUR": [row(90)], "USD": [row(100)]}})
    assert len(facts) == 1 and facts[0].value == "100" and facts[0].unit == "USD"


def test_q4_differencing_requires_same_filing():
    annual = row(400)
    nine_months = row(280, end="2025-03-31")
    facts = parse({"Revenues": {"USD": [annual, nine_months]}})
    derived, _ = calculate_financials(facts)
    assert [(f.value, f.period_start, f.period_end) for f in derived] == [
        ("120", date(2025, 4, 1), date(2025, 6, 30))
    ]
    nine_months["accn"] = "0000000001-25-000003"
    derived, gaps = calculate_financials(parse({"Revenues": {"USD": [annual, nine_months]}}))
    assert not derived and gaps


def test_four_contiguous_quarters_ttm_and_gaps():
    periods = [
        ("2024-07-01", "2024-09-30"),
        ("2024-10-01", "2024-12-31"),
        ("2025-01-01", "2025-03-31"),
        ("2025-04-01", "2025-06-30"),
    ]
    rows = [row(n + 1, start=a, end=b) for n, (a, b) in enumerate(periods)]
    derived, _ = calculate_financials(parse({"Revenues": {"USD": rows}}))
    assert len(derived) == 1 and derived[0].value == "10"
    assert len(derived[0].operand_evidence_ids) == 4
    rows[1]["start"] = "2024-10-02"
    assert calculate_financials(parse({"Revenues": {"USD": rows}}))[0] == []


@pytest.mark.parametrize("capex,expected", [(20, "80"), (-20, None)])
def test_cashflow_sign_is_explicit(capex, expected):
    facts = parse(
        {
            "NetCashProvidedByUsedInOperatingActivities": {"USD": [row(100)]},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"USD": [row(capex)]},
        }
    )
    derived, _ = calculate_financials(facts)
    fcf = [f for f in derived if f.metric == "free_cash_flow"]
    assert ([f.value for f in fcf] or [None]) == [expected]


def test_http_to_typed_result(monkeypatch):
    monkeypatch.setenv("EDGAR_CONTACT_EMAIL", "test@example.invalid")
    requested = []

    def handle(request):
        requested.append(str(request.url))
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"ticker": "MSFT", "cik_str": 1}})
        if "/submissions/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "filings": {
                        "recent": {
                            "accessionNumber": [row()["accn"]],
                            "primaryDocument": ["filing.htm"],
                            "acceptanceDateTime": ["2025-07-30T14:00:00Z"],
                        }
                    }
                },
            )
        return httpx.Response(200, json=company({"Revenues": {"USD": [row()]}}))

    args = parse_fundamentals_lookup_arguments('{"symbol":"MSFT","asOfDate":"2025-08-01"}')
    result = lookup_financials(SecFinancialsProvider(transport=httpx.MockTransport(handle)), args)
    assert len(requested) == 3
    assert result["financialFacts"][0]["value"] == "100"
    assert result["evidence"][0]["url"].endswith("/filing.htm")
    assert result["evidence"][0]["publishedAt"] == "2025-07-30T14:00:00Z"
    assert result["statements"][0]["lines"][0]["value"] == "100"
    assert result["cutoffAt"] == "2025-08-02T04:00:00Z"
    assert "test@example.invalid" not in str(result)


def test_missing_contact_degrades_without_network(monkeypatch):
    monkeypatch.delenv("EDGAR_CONTACT_EMAIL", raising=False)
    args = parse_fundamentals_lookup_arguments('{"symbol":"NVDA"}')
    result = lookup_financials(SecFinancialsProvider(), args)
    assert result["gaps"][0]["code"] == "source_unavailable"
    assert result["financialFacts"] == []


def test_weighted_shares_are_never_summed_or_differenced():
    facts = parse(
        {
            "WeightedAverageNumberOfSharesOutstandingBasic": {
                "shares": [row(100), row(90, end="2025-03-31")]
            }
        }
    )
    assert calculate_financials(facts)[0] == []


def test_eps_and_margin_retain_distinct_share_bases():
    from finance_plugin.research_financials_ratios import calculate_ratios

    facts = parse(
        {
            "NetIncomeLoss": {"USD": [row(100)]},
            "Revenues": {"USD": [row(400)]},
            "WeightedAverageNumberOfSharesOutstandingBasic": {"shares": [row(20)]},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"shares": [row(25)]},
        }
    )
    derived, _ = calculate_ratios(facts)
    assert {f.metric: (f.value, f.unit) for f in derived} == {
        "eps_basic": ("5.000000", "USD/share"),
        "eps_diluted": ("4.000000", "USD/share"),
        "net_margin": ("25.000000", "%"),
    }


def test_instant_debt_missing_components_are_not_zero():
    from finance_plugin.research_financials_ratios import calculate_ratios

    tags = {
        "CashAndCashEquivalentsAtCarryingValue": {"USD": [row(100, start=None)]},
        "LongTermDebtNoncurrent": {"USD": [row(20, start=None)]},
    }
    derived, gaps = calculate_ratios(parse(tags))
    assert not derived and any(g.metric == "total_debt" for g in gaps)
    tags.update(
        {
            "ShortTermBorrowings": {"USD": [row(0, start=None)]},
            "LongTermDebtCurrent": {"USD": [row(5, start=None)]},
        }
    )
    derived, _ = calculate_ratios(parse(tags))
    assert derived[0].value == "25"


def test_frozen_cutoff_excludes_later_publication(monkeypatch):
    monkeypatch.setenv("EDGAR_CONTACT_EMAIL", "test@example.invalid")

    def handle(request):
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"ticker": "MSFT", "cik_str": 1}})
        if "/submissions/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "filings": {
                        "recent": {
                            "accessionNumber": [row()["accn"]],
                            "acceptanceDateTime": ["2025-07-30T15:00:00Z"],
                        }
                    }
                },
            )
        return httpx.Response(200, json=company({"Revenues": {"USD": [row()]}}))

    args = parse_fundamentals_lookup_arguments(
        '{"symbol":"MSFT","cutoffAt":"2025-07-30T14:00:00Z"}'
    )
    result = lookup_financials(SecFinancialsProvider(transport=httpx.MockTransport(handle)), args)
    assert result["evidence"] == [] and not result["coverage"][0]["complete"]
    assert result["cutoffAt"] == "2025-07-30T14:00:00Z"


def test_financial_derived_evidence_is_recomputable_by_report_validator():
    from finance_plugin.research_financials import _evidence
    from finance_plugin.research_financials_ratios import calculate_ratios
    from finance_plugin.research_report_validation import derived_problem

    facts = parse(
        {
            "NetIncomeLoss": {"USD": [row(100)]},
            "Revenues": {"USD": [row(400)]},
            "WeightedAverageNumberOfSharesOutstandingBasic": {"shares": [row(20)]},
            "NetCashProvidedByUsedInOperatingActivities": {"USD": [row(100)]},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"USD": [row(20)]},
        }
    )
    financials, _ = calculate_financials(facts)
    ratios, _ = calculate_ratios(facts)
    evidence = [
        _evidence(f, "0000000001", "MSFT", {}, datetime.now(UTC))
        for f in facts + financials + ratios
    ]
    by_id = {item.evidence_id: item for item in evidence}
    assert all(derived_problem(item, by_id) is None for item in evidence if item.formula)


def test_productive_assets_are_a_distinct_cashflow_basis():
    facts = parse(
        {
            "NetCashProvidedByUsedInOperatingActivities": {"USD": [row(100)]},
            "PaymentsToAcquireProductiveAssets": {"USD": [row(20)]},
        }
    )
    derived, _ = calculate_financials(facts)
    assert derived[0].value == "80"
    assert derived[0].formula_version == "operating_cash_flow_minus_productive_assets/1"
    assert any(f.metric == "productive_asset_expenditures" for f in facts)


def test_identical_revenue_aliases_do_not_create_conflicts():
    facts, gaps = parse_facts(
        company(
            {
                "Revenues": {"USD": [row(100)]},
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"USD": [row(100)]},
            }
        ),
        {},
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert len(facts) == 1 and facts[0].alias_tags == ["Revenues"]
    assert not any(g.code == "ambiguous_concept" for g in gaps)


def test_current_output_does_not_report_old_cashflow_gaps():
    class Provider:
        def fetch(self, *args, **kwargs):
            raw = company(
                {
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "USD": [
                            row(100),
                            row(80, start="2011-07-01", end="2012-06-30", filed="2012-07-30"),
                        ]
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {"USD": [row(20)]},
                }
            )
            now = datetime(2026, 1, 1, tzinfo=UTC)
            facts, gaps = parse_facts(raw, {}, now)
            return "0000000001", now, now, facts, {}, gaps

    result = lookup_financials(
        Provider(), parse_fundamentals_lookup_arguments('{"symbol":"MSFT","statementLimit":1}')
    )
    assert all("2012" not in message for message in result["gapMessages"])
    assert not any(g["metric"] == "free_cash_flow" for g in result["gaps"])


def test_dei_cover_shares_keep_actual_observation_date():
    raw = {
        "cik": 1,
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [row(20, start=None, end="2025-07-25")]}
                }
            }
        },
    }
    facts, _ = parse_facts(raw, {}, datetime(2026, 1, 1, tzinfo=UTC))
    assert facts[0].taxonomy == "dei" and facts[0].period_end == date(2025, 7, 25)


def test_valuation_is_explicit_unverified_estimate_and_no_fake_ev():
    from finance_plugin.research_evidence import ResearchEvidence
    from finance_plugin.research_valuation import calculate_valuation

    values = dict(
        kind="observation",
        title="value",
        publication_date=date(2025, 8, 1),
        retrieved_at=datetime(2025, 8, 2, tzinfo=UTC),
        symbol="MSFT",
        verified=True,
    )
    price = ResearchEvidence(
        evidence_id="price",
        source_id="market",
        metric="market.close",
        value="10",
        unit="USD",
        currency="USD",
        period_end=date(2025, 8, 1),
        **values,
    )
    shares = ResearchEvidence(
        evidence_id="shares",
        source_id="sec:1",
        metric="shares_outstanding",
        value="20",
        unit="shares",
        period_end=date(2025, 7, 25),
        **values,
    )
    result, gaps = calculate_valuation([price, shares])
    assert len(result) == 1 and result[0].value == "200"
    assert result[0].verified is False and "splits" in result[0].uncertainty_reason
    assert any("EV unavailable" in gap for gap in gaps)


def test_three_revisions_preserve_history_but_reject_old_report_claims():
    from finance_plugin.research_financials import _evidence
    from finance_plugin.research_report import compile_research_report

    facts = parse(
        {
            "Revenues": {
                "USD": [
                    row(100),
                    row(110, filed="2025-08-10", acc="0000000001-25-000002"),
                    row(120, filed="2025-09-10", acc="0000000001-25-000003"),
                ]
            }
        }
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = [_evidence(fact, "0000000001", "MSFT", {}, now) for fact in facts]
    assert [item.verified for item in evidence] == [False, False, True]
    assert "仅保留历史出处" in evidence[0].uncertainty_reason
    assert evidence[2].supersedes_evidence_id == evidence[1].evidence_id
    assert evidence[1].supersedes_evidence_id == evidence[0].evidence_id
    result = compile_research_report(
        {
            "symbol": "MSFT",
            "asOfDate": "2026-01-01",
            "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence],
            "claims": [
                {
                    "claimId": "old-revenue",
                    "metric": "revenue",
                    "formula": "identity",
                    "evidenceIds": [evidence[0].evidence_id],
                    "value": "100",
                    "unit": "USD",
                    "periodStart": "2024-07-01",
                    "periodEnd": "2025-06-30",
                }
            ],
        },
        now=now,
    )
    assert result["status"] == "insufficient_evidence"
    assert any("old-revenue" in gap for gap in result["dataGaps"])
    assert len(result["evidence"]) == 3
    assert all(item.evidence_id in result["content"] for item in evidence)
