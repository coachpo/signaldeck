"""Explicit valuation estimates from dated prices and reported share counts."""

from decimal import Decimal

from .research_evidence import ResearchEvidence
from .research_financials_sec import identifier


def calculate_valuation(evidence: list[ResearchEvidence]):
    superseded = {item.supersedes_evidence_id for item in evidence if item.supersedes_evidence_id}
    usable = [
        item
        for item in evidence
        if item.verified
        and item.value is not None
        and item.period_end is not None
        and item.evidence_id not in superseded
    ]
    estimates, gaps = [], []
    symbols = {item.symbol for item in usable if item.symbol}
    for symbol in sorted(symbols):
        prices = [
            item
            for item in usable
            if item.symbol == symbol
            and item.metric == "market.close"
            and item.unit == "USD"
            and item.currency == "USD"
        ]
        shares = [
            item
            for item in usable
            if item.symbol == symbol
            and item.metric == "shares_outstanding"
            and item.unit == "shares"
            and item.period_start is None
        ]
        if not prices or not shares:
            gaps.append(
                f"{symbol}: valuation unavailable without dated USD close and outstanding shares."
            )
            continue
        price_date = max(item.period_end for item in prices)
        prices = [item for item in prices if item.period_end == price_date]
        shares = [item for item in shares if item.period_end <= price_date]
        if not shares:
            gaps.append(f"{symbol}: all reported share dates follow the price date.")
            continue
        share_date = max(item.period_end for item in shares)
        shares = [item for item in shares if item.period_end == share_date]
        if len(prices) != 1 or len(shares) != 1:
            gaps.append(f"{symbol}: conflicting same-date price or outstanding-share observations.")
            continue
        price, stock = prices[0], shares[0]
        if Decimal(price.value) <= 0 or Decimal(stock.value) <= 0:
            gaps.append(f"{symbol}: nonpositive price or outstanding shares; valuation omitted.")
            continue
        assumption = (
            f"Estimate: USD close at {price_date} multiplied by reported outstanding shares "
            f"at {share_date}; not current shares. Intervening splits, issuance and buybacks "
            "have not been reconciled. This is not a verified market-capitalization fact."
        )
        marketcap = _estimate(
            price,
            "market_cap_estimate",
            [price, stock],
            Decimal(price.value) * Decimal(stock.value),
            "price_times_reported_shares/1",
            assumption,
        )
        estimates.append(marketcap)
        gaps.append(f"{symbol}: {assumption}")
        cash = [
            item
            for item in usable
            if item.symbol == symbol
            and item.metric == "cash"
            and item.unit == "USD"
            and item.period_start is None
        ]
        debt = [
            item
            for item in usable
            if item.symbol == symbol
            and item.metric == "total_debt"
            and item.unit == "USD"
            and item.period_start is None
        ]
        pairs = [
            (c, d)
            for c in cash
            for d in debt
            if c.period_end == d.period_end
            and c.period_end <= price_date
            and c.accession == d.accession
        ]
        if not pairs:
            gaps.append(
                f"{symbol}: EV unavailable without same-date cash and complete debt; "
                "long-term debt alone is not total debt."
            )
            continue
        latest = max(c.period_end for c, _ in pairs)
        pairs = [(c, d) for c, d in pairs if c.period_end == latest]
        if len(pairs) != 1:
            gaps.append(f"{symbol}: conflicting cash/debt pairs; EV omitted.")
            continue
        cash_item, debt_item = pairs[0]
        rationale = (
            assumption + f" EV adds reported debt and subtracts cash at {latest}; "
            "lease treatment follows that debt basis."
        )
        estimates.append(
            _estimate(
                price,
                "enterprise_value_estimate",
                [marketcap, debt_item, cash_item],
                Decimal(marketcap.value) + Decimal(debt_item.value) - Decimal(cash_item.value),
                "marketcap_plus_debt_minus_cash/1",
                rationale,
            )
        )
    return estimates, gaps


def _estimate(price, metric, operands, value, formula, rationale):
    return ResearchEvidence(
        evidence_id=identifier(formula, *(item.evidence_id for item in operands)),
        source_id=price.source_id,
        kind="observation",
        title=f"{price.symbol} {metric}",
        url=price.url,
        published_at=price.published_at,
        publication_date=price.publication_date,
        retrieved_at=max(item.retrieved_at for item in operands),
        period_end=price.period_end,
        value=format(value, "f"),
        unit="USD",
        currency="USD",
        symbol=price.symbol,
        metric=metric,
        text=rationale,
        locator="Derived estimate; see inputEvidenceIds",
        verified=False,
        source_type="market",
        uncertainty_reason=rationale,
        formula=formula,
        input_evidence_ids=[item.evidence_id for item in operands],
    )
