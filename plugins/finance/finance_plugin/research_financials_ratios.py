"""Financial ratios require matching financial periods and explicit share bases."""

from decimal import ROUND_HALF_EVEN, Decimal

from .research_financials_calculations import _derived
from .research_financials_models import FinancialGap


def calculate_ratios(facts):
    facts = [fact for fact in facts if fact.selected]
    results, gaps = [], []
    for profit in (f for f in facts if f.metric == "net_income"):
        for denominator, metric, unit, multiplier in (
            ("weighted_average_shares", "eps_basic", "USD/share", Decimal(1)),
            ("diluted_weighted_average_shares", "eps_diluted", "USD/share", Decimal(1)),
            ("revenue", "net_margin", "%", Decimal(100)),
        ):
            matches = [
                f
                for f in facts
                if f.metric == denominator
                and f.period_start == profit.period_start
                and f.period_end == profit.period_end
                and f.period_type == profit.period_type
                and f.accession == profit.accession
            ]
            # Summing quarterly weighted-average shares is not a valid TTM denominator.
            if profit.period_type == "trailing_twelve_months":
                continue
            if len(matches) != 1 or Decimal(matches[0].value) == 0:
                gaps.append(
                    FinancialGap(
                        code="calculation_gap",
                        metric=metric,
                        period_end=profit.period_end,
                        message=f"Missing unique nonzero same-period {denominator}.",
                    )
                )
                continue
            divisor = matches[0]
            value = (Decimal(profit.value) / Decimal(divisor.value) * multiplier).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_EVEN
            )
            result = _derived(
                metric,
                [profit, divisor],
                value,
                "net_margin_percent/1" if metric == "net_margin" else f"{metric}/1",
            )
            result.unit = unit
            result.currency = "USD" if metric.startswith("eps") else None
            result.rounding = "6 decimal places; ROUND_HALF_EVEN"
            results.append(result)
    for cash in (f for f in facts if f.metric == "cash" and f.period_type == "instant"):
        debt = []
        for metric in ("short_term_debt", "long_term_debt_current", "long_term_debt_noncurrent"):
            matches = [
                f
                for f in facts
                if f.metric == metric
                and f.period_end == cash.period_end
                and f.accession == cash.accession
                and f.unit == cash.unit
            ]
            if len(matches) != 1:
                break
            debt.extend(matches)
        if len(debt) != 3:
            aggregate = [
                f
                for f in facts
                if f.metric == "long_term_debt"
                and f.period_end == cash.period_end
                and f.accession == cash.accession
            ]
            if len(aggregate) == 1:
                continue
            gaps.append(
                FinancialGap(
                    code="calculation_gap",
                    metric="total_debt",
                    period_end=cash.period_end,
                    message=(
                        "Missing explicit short-term or current/noncurrent long-term debt; "
                        "missing debt is not zero."
                    ),
                )
            )
            continue
        results.append(
            _derived(
                "total_debt",
                debt,
                sum((Decimal(f.value) for f in debt), Decimal(0)),
                "debt_components_sum/1",
            )
        )
    return results, gaps
