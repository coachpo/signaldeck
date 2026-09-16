"""Deterministic checks; source authenticity is owned by the collector boundary."""

from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from zoneinfo import ZoneInfo

from finance_plugin.research_evidence import ResearchClaim, ResearchEvidence, ResearchThreshold

NY = ZoneInfo("America/New_York")


def day_end(day):
    return datetime.combine(day + timedelta(days=1), time.min, NY).astimezone(UTC)


def evidence_problem(item: ResearchEvidence, cutoff: datetime) -> str | None:
    if item.kind == "user" or item.source_type == "user" or not item.verified:
        return "unverified source"
    if not item.url or not item.locator:
        return "missing original URL or locator"
    if item.published_at is not None:
        if item.published_at >= cutoff:
            return "published outside cutoff"
        if item.published_at > item.retrieved_at:
            return "publication later than retrieval"
    elif item.publication_date is not None:
        if day_end(item.publication_date) > cutoff:
            return "date-only publication cannot establish intraday availability"
    elif item.available_by_date is not None:
        if day_end(item.available_by_date) > cutoff:
            return "known availability upper bound exceeds cutoff"
    else:
        return "publication time unknown"
    return None


def calculate(formula: str, values: list[Decimal]) -> Decimal:
    if formula == "identity" and len(values) == 1:
        return values[0]
    if formula == "sum" and values:
        return sum(values, Decimal(0))
    if formula == "difference" and len(values) == 2:
        return values[0] - values[1]
    if formula in ("ratio", "percent") and len(values) == 2 and values[1] != 0:
        return values[0] / values[1] * (100 if formula == "percent" else 1)
    raise ValueError("unsupported formula, operand count or zero denominator")


def claim_problem(claim: ResearchClaim, evidence: dict[str, ResearchEvidence]) -> str | None:
    if claim.kind != "fact":
        return "inference or user claim is not a verified fact"
    if len(set(claim.evidence_ids)) != len(claim.evidence_ids):
        return "repeated operand reference"
    if any(key not in evidence for key in claim.evidence_ids):
        return "missing or ineligible evidence reference"
    operands = [evidence[key] for key in claim.evidence_ids]
    if any(item.value is None for item in operands):
        return "non-numeric operand"
    if any(
        (item.period_start, item.period_end) != (claim.period_start, claim.period_end)
        for item in operands
    ):
        return "period mismatch"
    if len({item.unit for item in operands}) != 1 or len({item.currency for item in operands}) != 1:
        return "operand unit or currency mismatch"
    expected_unit = (
        "%"
        if claim.formula == "percent"
        else "ratio" if claim.formula == "ratio" else operands[0].unit
    )
    if claim.unit != expected_unit:
        return "result unit mismatch"
    if claim.formula == "identity" and operands[0].metric != claim.metric:
        return "identity metric mismatch"
    try:
        with localcontext() as context:
            context.prec = 150
            computed = calculate(claim.formula, [Decimal(item.value) for item in operands])
            quantum = Decimal(1).scaleb(-claim.decimal_places)
            if computed.quantize(quantum, rounding=ROUND_HALF_EVEN) != Decimal(claim.value):
                return "value does not match recomputation (ROUND_HALF_EVEN)"
    except (ValueError, ArithmeticError):
        return "invalid calculation or zero denominator"
    return None


def threshold_problem(threshold: ResearchThreshold, evidence: dict[str, ResearchEvidence]):
    observed = evidence.get(threshold.observed_evidence_id)
    if observed is None or observed.value is None:
        return "missing or ineligible observed evidence"
    signature = (threshold.metric, threshold.unit, threshold.period_start, threshold.period_end)

    def compatible(item):
        return (item.metric, item.unit, item.period_start, item.period_end) == signature

    if not compatible(observed):
        return "observation metric, unit or period mismatch"
    if threshold.basis == "hypothesis":
        return None
    if not threshold.evidence_ids or any(key not in evidence for key in threshold.evidence_ids):
        return "missing or ineligible threshold source"
    sources = [evidence[key] for key in threshold.evidence_ids]
    if any(not compatible(item) for item in sources):
        return "threshold source metric, unit or period mismatch"
    if threshold.center_evidence_id or threshold.tolerance_evidence_id:
        if not all(
            key in threshold.evidence_ids
            for key in (threshold.center_evidence_id, threshold.tolerance_evidence_id)
        ):
            return "center and tolerance must both reference threshold sources"
        center = evidence[threshold.center_evidence_id]
        tolerance = evidence[threshold.tolerance_evidence_id]
        if center.value is None or tolerance.value is None or Decimal(tolerance.value) < 0:
            return "invalid center or tolerance"
        lower = Decimal(center.value) - Decimal(tolerance.value)
        upper = Decimal(center.value) + Decimal(tolerance.value)
        if threshold.lower is None or threshold.upper is None:
            return "center/tolerance guidance requires both bounds"
        if (Decimal(threshold.lower), Decimal(threshold.upper)) != (lower, upper):
            return "bounds do not match center plus/minus tolerance"
    else:
        source_values = {Decimal(item.value) for item in sources if item.value is not None}
        if any(
            Decimal(bound) not in source_values
            for bound in (threshold.lower, threshold.upper)
            if bound is not None
        ):
            return "threshold bounds are not supported by cited values"
    return None


def derived_problem(item: ResearchEvidence, evidence: dict[str, ResearchEvidence]):
    """Recompute collector derivatives rather than trusting their verified flag."""
    if not item.input_evidence_ids:
        return "derived value has no operands" if item.formula else None
    if any(key not in evidence for key in item.input_evidence_ids):
        return "missing or ineligible derived operand"
    operands = [evidence[key] for key in item.input_evidence_ids]
    if item.value is None or any(operand.value is None for operand in operands):
        return "non-numeric derived operand"
    ratio_formula = item.formula in {"eps_basic/1", "eps_diluted/1", "net_margin_percent/1"}
    if not ratio_formula and len({operand.unit for operand in operands} | {item.unit}) != 1:
        return "derived unit mismatch"
    if not ratio_formula and len({operand.currency for operand in operands} | {item.currency}) != 1:
        return "derived currency mismatch"
    values = [Decimal(operand.value) for operand in operands]

    def signature(operand):
        return (operand.period_start, operand.period_end)

    try:
        with localcontext() as context:
            context.prec = 150
            if ratio_formula:
                if len(operands) != 2 or any(
                    signature(operand) != signature(item) for operand in operands
                ):
                    return "ratio requires two same-period operands"
                if len({operand.accession for operand in operands} | {item.accession}) != 1:
                    return "ratio requires one filing"
                expected_denominator = {
                    "eps_basic/1": "weighted_average_shares",
                    "eps_diluted/1": "diluted_weighted_average_shares",
                    "net_margin_percent/1": "revenue",
                }[item.formula]
                if operands[0].metric != "net_income" or operands[1].metric != expected_denominator:
                    return "ratio metric mismatch"
                margin = item.formula == "net_margin_percent/1"
                if operands[0].unit != "USD" or operands[1].unit != ("USD" if margin else "shares"):
                    return "ratio input unit mismatch"
                if item.unit != ("%" if margin else "USD/share"):
                    return "ratio result unit mismatch"
                computed = (values[0] / values[1] * (100 if margin else 1)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_EVEN
                )
            elif item.formula == "debt_components_sum/1":
                if len(operands) != 3 or any(
                    signature(operand) != signature(item) for operand in operands
                ):
                    return "debt requires three same-instant components"
                if (
                    item.period_start is not None
                    or len({operand.accession for operand in operands} | {item.accession}) != 1
                ):
                    return "debt requires one filing and instant periods"
                if {operand.metric for operand in operands} != {
                    "short_term_debt",
                    "long_term_debt_current",
                    "long_term_debt_noncurrent",
                }:
                    return "debt component mismatch"
                computed = sum(values, Decimal(0))
            elif item.formula == "cumulative_difference/1":
                if len(operands) != 2:
                    return "cumulative difference requires two operands"
                total, prior = operands
                if (
                    total.period_start is None
                    or prior.period_end is None
                    or total.period_end is None
                    or total.period_start != prior.period_start
                    or total.period_end <= prior.period_end
                    or total.tag != prior.tag
                    or total.accession != prior.accession
                    or item.period_start != prior.period_end + timedelta(days=1)
                    or item.period_end != total.period_end
                ):
                    return "incompatible cumulative periods or filings"
                computed = values[0] - values[1]
            elif item.formula == "four_contiguous_quarters/1":
                if len(operands) != 4:
                    return "TTM requires four quarters"
                ordered = sorted(
                    operands, key=lambda operand: operand.period_start or datetime.min.date()
                )
                if any(
                    operand.period_start is None
                    or operand.period_end is None
                    or not 70 <= (operand.period_end - operand.period_start).days <= 105
                    or operand.tag != item.tag
                    for operand in ordered
                ):
                    return "TTM requires actual quarterly periods and matching tags"
                if any(
                    right.period_start != left.period_end + timedelta(days=1)
                    for left, right in zip(ordered, ordered[1:], strict=False)
                ):
                    return "TTM quarters overlap or have gaps"
                if (item.period_start, item.period_end) != (
                    ordered[0].period_start,
                    ordered[-1].period_end,
                ):
                    return "TTM result period mismatch"
                computed = sum(values, Decimal(0))
            elif item.formula in {
                "operating_cash_flow_minus_positive_capex/1",
                "operating_cash_flow_minus_productive_assets/1",
            }:
                if len(operands) != 2 or any(
                    signature(operand) != signature(item) for operand in operands
                ):
                    return "FCF requires two same-period operands"
                if item.formula == "operating_cash_flow_minus_productive_assets/1" and (
                    operands[0].metric != "operating_cash_flow"
                    or operands[1].metric != "productive_asset_expenditures"
                ):
                    return "productive-asset cash flow input metric mismatch"
                if values[1] < 0:
                    return "capital expenditure must be positive"
                computed = values[0] - values[1]
            else:
                if any(signature(operand) != signature(item) for operand in operands):
                    return "derived period mismatch"
                computed = calculate(item.formula or "", values)
            if computed != Decimal(item.value):
                return "derived value does not match recomputation"
    except (ValueError, ArithmeticError):
        return "invalid derived calculation"
    return None
