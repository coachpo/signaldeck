"""Project SEC fundamentals into traceable research and existing statement outputs."""

from datetime import UTC, datetime, time
from decimal import Decimal

import httpx

from .contracts import RuntimeToolWarning
from .providers.market_data_snapshots import (
    MarketDataFinancialStatement,
    MarketDataFinancialStatementLine,
)
from .research_evidence import ResearchEvidence
from .research_financials_calculations import calculate_financials
from .research_financials_models import FinancialCoverage, FinancialGap
from .research_financials_ratios import calculate_ratios
from .research_financials_sec import NY, research_cutoff


def lookup_financials(provider, arguments):
    from .runtime_types import RuntimeFundamentalsLookupResult

    symbol = arguments["symbol"]
    as_of = arguments.get("as_of_date")
    now = datetime.now(UTC)
    try:
        cik, observed, cutoff, facts, filings, gaps = provider.fetch(
            symbol, as_of, now=now, cutoff_at=arguments.get("cutoff_at")
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Provider exception text can contain request headers or URL credentials.
        return RuntimeFundamentalsLookupResult(
            symbol=symbol,
            provider="sec",
            as_of=now,
            as_of_date=as_of or now.astimezone(NY).date(),
            cutoff_at=min(research_cutoff(as_of, now), arguments.get("cutoff_at") or now),
            coverage=[
                FinancialCoverage(
                    source_id="sec",
                    complete=False,
                    observed_at=now,
                    warning="SEC source unavailable",
                )
            ],
            gaps=[
                FinancialGap(
                    code="source_unavailable",
                    metric="all",
                    message=(
                        "SEC financials unavailable; check deployment contact "
                        "configuration and SEC service availability."
                    ),
                )
            ],
            gap_messages=["SEC financials unavailable"],
            warnings=[
                RuntimeToolWarning(
                    code="fundamentals_unavailable", message="SEC financials unavailable"
                )
            ],
        ).model_dump(mode="json", by_alias=True)
    derived, calculation_gaps = calculate_financials(facts)
    ratios, ratio_gaps = calculate_ratios(facts + derived)
    calculation_gaps.extend(ratio_gaps)
    all_facts = facts + derived + ratios
    # Bounds apply to periods, never arbitrarily to fields within a statement.
    end_dates = sorted(
        {f.period_end for f in all_facts if f.selected and f.period_type != "instant"}, reverse=True
    )[: arguments["statement_limit"]]
    selected = _select_periods(all_facts, end_dates)
    by_id = {f.evidence_id: f for f in all_facts}
    included = _dependency_closure(selected, by_id)
    while len(included) > 280 and len(end_dates) > 1:
        end_dates.pop()
        selected = _select_periods(all_facts, end_dates)
        included = _dependency_closure(selected, by_id)
        gaps.append(
            FinancialGap(
                code="output_bounded",
                metric="all",
                message=(
                    "Oldest periods omitted to preserve complete operand "
                    "references within the evidence budget."
                ),
            )
        )
    if len(included) > 280:
        selected = []
        included = {}
        gaps.append(
            FinancialGap(
                code="output_bounded",
                metric="all",
                message=(
                    "Latest period exceeds evidence budget including revisions; no "
                    "partial financial statement emitted."
                ),
            )
        )
    # Diagnostics describe returned periods, never the issuer's entire API history.
    gaps = [
        gap
        for gap in gaps + calculation_gaps
        if gap.code != "metric_missing" and (gap.period_end is None or gap.period_end in end_dates)
    ]
    required_metrics = {
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "operating_cash_flow",
        "cash",
        "shares_outstanding",
    }
    for metric in required_metrics:
        if not any(f.metric == metric for f in selected):
            gaps.append(
                FinancialGap(
                    code="metric_missing",
                    metric=metric,
                    message="No supported fact in the selected financial periods.",
                )
            )
    if any(f.metric == "productive_asset_expenditures" for f in selected):
        gaps.append(
            FinancialGap(
                code="capex_basis",
                metric="free_cash_flow",
                message=(
                    "Productive-asset expenditure includes PP&E, software and other "
                    "intangibles; FCF uses this explicitly broader basis."
                ),
            )
        )
    if any(f.metric == "long_term_debt" for f in selected) and not any(
        f.metric == "total_debt" for f in selected
    ):
        gaps.append(
            FinancialGap(
                code="debt_basis",
                metric="long_term_debt",
                message=(
                    "Reported aggregate long-term debt retained; current/noncurrent "
                    "components are not added again. Absence of short-term borrowing "
                    "disclosure does not establish zero."
                ),
            )
        )
    evidence = [_evidence(f, cik, symbol, filings, observed) for f in included.values()]
    return RuntimeFundamentalsLookupResult(
        symbol=symbol,
        provider="sec",
        as_of=observed,
        cik=cik,
        as_of_date=as_of or observed.astimezone(NY).date(),
        cutoff_at=cutoff,
        financial_facts=list(included.values()),
        evidence=evidence,
        coverage=[
            FinancialCoverage(
                source_id="sec",
                complete=any(item.verified for item in evidence),
                observed_at=observed,
                evidence_ids=[item.evidence_id for item in evidence if item.verified],
                warning="Standard US GAAP only; see gaps",
            ),
            *(
                [
                    FinancialCoverage(
                        source_id="sec_history",
                        complete=False,
                        observed_at=observed,
                        evidence_ids=[item.evidence_id for item in evidence if not item.verified],
                        warning="Superseded disclosures retained for historical provenance only.",
                    )
                ]
                if any(not item.verified for item in evidence)
                else []
            ),
        ],
        gaps=gaps,
        gap_messages=list(dict.fromkeys(f"{g.code} [{g.metric}]: {g.message}" for g in gaps)),
        statements=_statements(selected, arguments),
        warnings=[
            RuntimeToolWarning(
                code="sec_coverage_limit",
                message=(
                    "Entity-wide standard US GAAP only; no valuation or consensus "
                    "estimates. Fiscal focus metadata does not define the fact "
                    "period."
                ),
            )
        ],
    ).model_dump(mode="json", by_alias=True)


def _evidence(fact, cik, symbol, filings, retrieved):
    primary = filings.get(fact.accession, {}).get("primaryDocument")
    root = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{fact.accession.replace('-', '')}"
    url = f"{root}/{primary}" if primary else f"{root}/{fact.accession}-index.html"
    return ResearchEvidence(
        evidence_id=fact.evidence_id,
        source_id=fact.source_id,
        kind="fact",
        title=f"{symbol} {fact.metric} {fact.period_type} {fact.period_end}",
        url=url,
        published_at=fact.accepted_at,
        publication_date=None if fact.accepted_at else fact.filed_at,
        retrieved_at=retrieved,
        period_start=fact.period_start,
        period_end=fact.period_end,
        value=fact.value,
        unit=fact.unit,
        text=fact.excerpt
        + ("; identical aliases: " + ", ".join(fact.alias_tags) if fact.alias_tags else ""),
        locator=fact.locator,
        accession=fact.accession,
        metric=fact.metric,
        verified=fact.selected,
        source_type="sec",
        uncertainty_reason=(
            "SEC filing focus fy/fp retained; actual period classified by "
            "start/end. XBRL excerpt, not a claim to have read filing "
            "prose."
        )
        + (
            " 已被截止前后续修订替代，仅保留历史出处；原始披露仍保留。" if not fact.selected else ""
        ),
        symbol=symbol,
        currency=fact.currency,
        taxonomy=fact.taxonomy,
        tag=fact.tag,
        form=fact.form,
        fiscal_year=fact.fiscal_year,
        fiscal_period=fact.fiscal_period,
        formula=fact.formula_version,
        input_evidence_ids=fact.operand_evidence_ids,
        supersedes_evidence_id=(
            fact.supersedes_evidence_ids[-1] if fact.supersedes_evidence_ids else None
        ),
    )


def _statements(facts, arguments):
    groups = {}
    for fact in facts:
        if fact.period_type in {"year_to_date", "other", "instant"}:
            # An instant is not intrinsically an annual/quarterly reporting period.
            continue
        statement_type = (
            "cash_flow"
            if fact.metric
            in {
                "operating_cash_flow",
                "capital_expenditures",
                "productive_asset_expenditures",
                "free_cash_flow",
            }
            else "income_statement"
        )
        if arguments["statement_types"] and statement_type not in arguments["statement_types"]:
            continue
        if arguments["periods"] and fact.period_type not in arguments["periods"]:
            continue
        groups.setdefault(
            (statement_type, fact.period_type, fact.period_start, fact.period_end), []
        ).append(fact)
    statements = []
    for (kind, period, _start, end), rows in groups.items():
        # Conflicting aliases are visible in facts, never duplicated under one line name.
        counts = {f.metric: sum(r.metric == f.metric for r in rows) for f in rows}
        statements.append(
            MarketDataFinancialStatement(
                statement_type=kind,
                period=period,
                period_end=datetime.combine(end, time.min, UTC),
                lines=[
                    MarketDataFinancialStatementLine(
                        name=f.metric, value=Decimal(f.value), currency=f.currency
                    )
                    for f in rows
                    if counts[f.metric] == 1
                ],
            )
        )
    return sorted(statements, key=lambda s: s.period_end, reverse=True)[
        : arguments["statement_limit"]
    ]


def _dependency_closure(selected, by_id):
    included = {f.evidence_id: f for f in selected}
    pending = list(selected)
    while pending:
        fact = pending.pop()
        for evidence_id in fact.operand_evidence_ids + fact.supersedes_evidence_ids:
            if evidence_id in by_id and evidence_id not in included:
                included[evidence_id] = by_id[evidence_id]
                pending.append(by_id[evidence_id])
    return included


def _select_periods(facts, end_dates):
    share_dates = [f.period_end for f in facts if f.selected and f.metric == "shares_outstanding"]
    latest_shares = max(share_dates) if share_dates else None
    return [
        f
        for f in facts
        if f.selected
        and (
            f.period_end in end_dates
            or (f.metric == "shares_outstanding" and f.period_end == latest_shares)
        )
    ]
