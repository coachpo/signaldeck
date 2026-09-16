"""Conservative period arithmetic over traceable SEC financial facts."""

from datetime import timedelta
from decimal import Decimal

from .research_financials_models import FinancialFact, FinancialGap
from .research_financials_sec import identifier


def _derived(metric, operands, value, formula, *, start=None, end=None, period=None):
    newest = max(operands, key=lambda f: (f.filed_at, f.accession))
    return newest.model_copy(
        update={
            "evidence_id": identifier(formula, *(f.evidence_id for f in operands)),
            "metric": metric,
            "value": format(value, "f"),
            "period_start": start or newest.period_start,
            "period_end": end or newest.period_end,
            "period_type": period or newest.period_type,
            "operand_evidence_ids": [f.evidence_id for f in operands],
            "formula_version": formula,
            "rounding": "exact decimal; no rounding",
            "supersedes_evidence_ids": [],
            "excerpt": f"{formula}: {format(value, 'f')} {newest.unit}",
        }
    )


def calculate_financials(facts: list[FinancialFact]):
    selected = [fact for fact in facts if fact.selected]
    derived: list[FinancialFact] = []
    gaps: list[FinancialGap] = []
    # Differencing requires the same filing, concept and unit. A later restatement
    # must not silently be subtracted from an unrevised earlier cumulative fact.
    for total in selected:
        if "weighted_average_shares" in total.metric:
            continue
        if total.period_type not in {"year_to_date", "annual"}:
            continue
        prior = [
            f
            for f in selected
            if f.metric == total.metric
            and f.tag == total.tag
            and f.unit == total.unit
            and f.accession == total.accession
            and f.period_start == total.period_start
            and f.period_end < total.period_end
            and 77 <= (total.period_end - f.period_end).days <= 105
        ]
        if len(prior) == 1:
            base = prior[0]
            start = base.period_end + timedelta(days=1)
            if not any(
                f.metric == total.metric
                and f.tag == total.tag
                and f.unit == total.unit
                and f.period_start == start
                and f.period_end == total.period_end
                for f in selected
            ):
                derived.append(
                    _derived(
                        total.metric,
                        [total, base],
                        Decimal(total.value) - Decimal(base.value),
                        "cumulative_difference/1",
                        start=start,
                        period="quarterly",
                    )
                )
    quarters = [f for f in selected + derived if f.period_type == "quarterly"]
    for latest in quarters:
        if "weighted_average_shares" in latest.metric:
            continue
        chain = [latest]
        while len(chain) < 4:
            previous = [
                f
                for f in quarters
                if f.metric == latest.metric
                and f.tag == latest.tag
                and f.unit == latest.unit
                and f.currency == latest.currency
                and f.period_end + timedelta(days=1) == chain[-1].period_start
            ]
            if len(previous) != 1:
                break
            chain.append(previous[0])
        if len(chain) == 4:
            derived.append(
                _derived(
                    latest.metric,
                    list(reversed(chain)),
                    sum((Decimal(f.value) for f in chain), Decimal(0)),
                    "four_contiguous_quarters/1",
                    start=chain[-1].period_start,
                    end=latest.period_end,
                    period="trailing_twelve_months",
                )
            )
    pool = selected + derived
    for cashflow in pool:
        if cashflow.metric != "operating_cash_flow":
            continue
        capex = [
            f
            for f in pool
            if f.metric in {"capital_expenditures", "productive_asset_expenditures"}
            and f.unit == cashflow.unit
            and f.period_start == cashflow.period_start
            and f.period_end == cashflow.period_end
            and f.period_type == cashflow.period_type
            and f.currency == cashflow.currency
            and (
                f.accession == cashflow.accession
                or (f.formula_version is not None and f.formula_version == cashflow.formula_version)
            )
        ]
        if len(capex) == 1 and Decimal(capex[0].value) >= 0:
            derived.append(
                _derived(
                    "free_cash_flow",
                    [cashflow, capex[0]],
                    Decimal(cashflow.value) - Decimal(capex[0].value),
                    (
                        "operating_cash_flow_minus_positive_capex/1"
                        if capex[0].metric == "capital_expenditures"
                        else "operating_cash_flow_minus_productive_assets/1"
                    ),
                )
            )
        else:
            gaps.append(
                FinancialGap(
                    code="calculation_gap",
                    metric="free_cash_flow",
                    period_end=cashflow.period_end,
                    message=(
                        f"No unique same-period positive capital expenditure fact for "
                        f"{cashflow.period_end}."
                    ),
                )
            )
    for metric in {
        f.metric
        for f in selected
        if f.period_type != "instant" and "weighted_average_shares" not in f.metric
    }:
        if not any(
            f.metric == metric and f.period_type == "trailing_twelve_months" for f in derived
        ):
            gaps.append(
                FinancialGap(
                    code="calculation_gap",
                    metric=metric,
                    period_end=max(f.period_end for f in selected if f.metric == metric),
                    message=(
                        "TTM requires four unique contiguous same-concept quarters; " "unavailable."
                    ),
                )
            )
    return derived, gaps
