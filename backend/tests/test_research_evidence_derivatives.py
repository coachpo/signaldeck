"""Collector arithmetic is independently checked at canonical report generation."""

import pytest

from tests.test_research_evidence import compile_report, evidence, request


def financial(key, value, start, end, **extra):
    return evidence(
        key,
        value,
        periodStart=start,
        periodEnd=end,
        unit="USD",
        currency="USD",
        metric="operating_cash_flow",
        tag="NetCashProvidedByUsedInOperatingActivities",
        accession="2026-filing",
        **extra,
    )


def test_q4_uses_same_filing_cumulative_difference():
    args = request()
    args["evidence"] = [
        financial("year", "100", "2025-01-01", "2025-12-31"),
        financial("nine", "70", "2025-01-01", "2025-09-30"),
        financial(
            "q4",
            "30",
            "2025-10-01",
            "2025-12-31",
            formula="cumulative_difference/1",
            inputEvidenceIds=["year", "nine"],
        ),
    ]
    args["claims"][0].update(
        metric="operating_cash_flow",
        value="30",
        unit="USD",
        evidenceIds=["q4"],
        periodStart="2025-10-01",
        periodEnd="2025-12-31",
    )
    assert compile_report(args)["status"] == "validated"
    args["evidence"][1]["accession"] = "different-filing"
    assert any("incompatible cumulative" in gap for gap in compile_report(args)["dataGaps"])


@pytest.mark.parametrize("fault", ["gap", "overlap", "annual", "unit", "currency"])
def test_ttm_only_combines_four_compatible_actual_quarters(fault):
    args = request()
    periods = [
        ("2025-01-01", "2025-03-31"),
        ("2025-04-01", "2025-06-30"),
        ("2025-07-01", "2025-09-30"),
        ("2025-10-01", "2025-12-31"),
    ]
    args["evidence"] = [
        financial(f"q{i}", "10", start, end) for i, (start, end) in enumerate(periods)
    ]
    args["evidence"].append(
        financial(
            "ttm",
            "40",
            "2025-01-01",
            "2025-12-31",
            formula="four_contiguous_quarters/1",
            inputEvidenceIds=["q0", "q1", "q2", "q3"],
        )
    )
    args["claims"][0].update(
        metric="operating_cash_flow",
        value="40",
        unit="USD",
        evidenceIds=["ttm"],
        periodStart="2025-01-01",
        periodEnd="2025-12-31",
    )
    assert compile_report(args)["status"] == "validated"
    field, value = {
        "gap": ("periodStart", "2025-04-02"),
        "overlap": ("periodStart", "2025-03-31"),
        "annual": ("periodStart", "2024-04-01"),
        "unit": ("unit", "EUR"),
        "currency": ("currency", "EUR"),
    }[fault]
    args["evidence"][1][field] = value
    assert compile_report(args)["status"] == "insufficient_evidence"


def test_fcf_does_not_flip_capex_sign():
    args = request()
    args["evidence"] = [
        financial("operating", "100", "2025-01-01", "2025-12-31"),
        financial("capex", "30", "2025-01-01", "2025-12-31"),
        financial(
            "fcf",
            "70",
            "2025-01-01",
            "2025-12-31",
            formula="operating_cash_flow_minus_positive_capex/1",
            inputEvidenceIds=["operating", "capex"],
        ),
    ]
    args["claims"][0].update(
        metric="operating_cash_flow",
        value="70",
        unit="USD",
        evidenceIds=["fcf"],
        periodStart="2025-01-01",
        periodEnd="2025-12-31",
    )
    assert compile_report(args)["status"] == "validated"
    args["evidence"][1]["value"] = "-30"
    args["evidence"][2]["value"] = "130"
    assert any("capital expenditure" in gap for gap in compile_report(args)["dataGaps"])


@pytest.mark.parametrize(
    "formula,denominator,unit,result",
    [
        ("eps_basic/1", "weighted_average_shares", "USD/share", "3.333333"),
        ("eps_diluted/1", "diluted_weighted_average_shares", "USD/share", "3.333333"),
        ("net_margin_percent/1", "revenue", "%", "333.333333"),
    ],
)
def test_financial_ratios_recompute_units_and_share_kind(formula, denominator, unit, result):
    args = request()
    first = financial("numerator", "10", "2025-01-01", "2025-12-31")
    first["metric"] = "net_income"
    second = financial("denominator", "3", "2025-01-01", "2025-12-31")
    second.update(metric=denominator, unit="USD" if denominator == "revenue" else "shares")
    derived = financial(
        "derived",
        result,
        "2025-01-01",
        "2025-12-31",
        formula=formula,
        inputEvidenceIds=["numerator", "denominator"],
    )
    derived.update(metric="result", unit=unit)
    args["evidence"] = [first, second, derived]
    args["claims"][0].update(
        metric="result",
        value=result,
        unit=unit,
        evidenceIds=["derived"],
        periodStart="2025-01-01",
        periodEnd="2025-12-31",
    )
    assert compile_report(args)["status"] == "validated"
    args["evidence"][1]["metric"] = "shares_outstanding"
    assert any("ratio metric mismatch" in gap for gap in compile_report(args)["dataGaps"])


def test_broader_productive_asset_formula_keeps_its_own_metric():
    args = request()
    cash = financial("operating", "100", "2025-01-01", "2025-12-31")
    spending = financial("spending", "30", "2025-01-01", "2025-12-31")
    spending["metric"] = "productive_asset_expenditures"
    result = financial(
        "fcf",
        "70",
        "2025-01-01",
        "2025-12-31",
        formula="operating_cash_flow_minus_productive_assets/1",
        inputEvidenceIds=["operating", "spending"],
    )
    args["evidence"] = [cash, spending, result]
    args["claims"][0].update(
        metric="operating_cash_flow",
        value="70",
        unit="USD",
        evidenceIds=["fcf"],
        periodStart="2025-01-01",
        periodEnd="2025-12-31",
    )
    assert compile_report(args)["status"] == "validated"
    args["evidence"][1]["metric"] = "capital_expenditures"
    assert any("productive-asset" in gap for gap in compile_report(args)["dataGaps"])
