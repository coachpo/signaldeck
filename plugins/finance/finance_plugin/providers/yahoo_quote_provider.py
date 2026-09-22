"""Yahoo Finance market data, insider rows, holders and analyst estimates read through yfinance."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TypeVar
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from plugin_runtime.formatting import normalize_currency, normalize_symbol, to_utc

from ..estimate_contracts import (
    AnalystEstimatesSnapshot,
    EarningsSurprise,
    EpsRevisions,
    EpsTrend,
    EstimatePeriod,
    EstimateRange,
    PriceTarget,
    RatingChange,
    RecommendationCount,
)
from ..holder_contracts import HolderPosition, HoldersSnapshot, InsiderHolding, OwnershipBreakdown
from .quote_provider import (
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)

# Raise provider failures instead of letting yfinance log them and return empty frames.
yf.config.debug.hide_exceptions = False

_T = TypeVar("_T")
_PRICE_COLUMNS = ("Open", "High", "Low", "Close")
_RECOMMENDATIONS = ("strongBuy", "buy", "hold", "sell", "strongSell")
_TRANSACTION = re.compile(
    r"(?P<kind>.+?) at price (?P<price>\d+(?:\.\d+)?)(?P<range> - \d+(?:\.\d+)?)? per share\.?"
)


class YahooFinanceQuoteProvider:
    provider_name: str = "yahoo_finance"

    def __init__(
        self,
        timeout: float,
        ticker_factory: Callable[[str], yf.Ticker] = yf.Ticker,
    ) -> None:
        self.timeout: float = timeout
        self._ticker_factory = ticker_factory

    def fetch_symbol_name(self, symbol: str) -> str | None:
        _, meta = self._history(symbol, interval="1d", period="1d")
        return _name(meta)

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        _, meta = self._history(symbol, interval="1d", period="1d")
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        currency = meta.get("currency")
        if price is None or currency is None:
            raise QuoteProviderError(f"Quote payload was incomplete for {symbol}")

        return ProviderQuote(
            symbol=normalize_symbol(symbol),
            name=_name(meta),
            price=Decimal(str(price)),
            previous_close=(Decimal(str(previous_close)) if previous_close is not None else None),
            currency=normalize_currency(str(currency)),
            provider=self.provider_name,
            as_of=_moment(meta.get("regularMarketTime")),
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        frame, meta = self._history(symbol, interval=interval, period=range_value)
        points = [
            ProviderHistoryPoint(at=at, close=close)
            for at, bar in _bars(frame, meta, interval)
            if (close := _decimal(bar.get("Close"))) is not None
        ]
        if not points:
            raise QuoteProviderError(f"Historical quote payload was empty for {symbol}")

        return ProviderHistorySeries(
            symbol=normalize_symbol(symbol),
            currency=_currency(meta),
            provider=self.provider_name,
            points=points,
        )

    def fetch_ohlcv(
        self, symbol: str, *, start_date: datetime, end_date: datetime, interval: str
    ) -> ProviderOhlcvSeries:
        start, end = to_utc(start_date), to_utc(end_date)
        # Only the start bound goes to yfinance: it serves windows that ended in the past
        # from an in-process cache, and every read must return current provider data.
        frame, meta = self._history(symbol, interval=interval, start=start)
        rows: list[ProviderOhlcvRow] = []
        for at, bar in _bars(frame, meta, interval):
            prices = [_decimal(bar.get(column)) for column in _PRICE_COLUMNS]
            if not start <= at <= end or any(price is None for price in prices):
                continue
            open_price, high_price, low_price, close_price = prices
            rows.append(
                ProviderOhlcvRow(
                    at=at,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=_volume(bar.get("Volume")),
                    adjusted_close=_decimal(bar.get("Adj Close")),
                )
            )

        if not rows:
            raise QuoteProviderError(f"OHLCV payload was empty for {symbol}")

        return ProviderOhlcvSeries(
            symbol=normalize_symbol(symbol),
            currency=_currency(meta),
            provider=self.provider_name,
            rows=rows,
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        raise QuoteProviderError(
            f"Fundamentals are unavailable for {normalize_symbol(symbol)}",
            code="provider_unavailable",
            details={"provider": self.provider_name, "symbol": normalize_symbol(symbol)},
        )

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        frame = self._read(symbol, lambda ticker: ticker.insider_transactions)
        transactions: list[ProviderInsiderTransaction] = []
        for row in _records(frame):
            name, day = _text(row.get("Insider")), _day(row.get("Start Date"))
            if name is None or day is None:
                continue
            # Yahoo dates each row by its transaction; the filing time is not part of the row.
            at = datetime.combine(day, time.min, tzinfo=UTC)
            if (start_date is not None and at < to_utc(start_date)) or (
                end_date is not None and at > to_utc(end_date)
            ):
                continue
            kind, price = _transaction(_text(row.get("Text")))
            transactions.append(
                ProviderInsiderTransaction(
                    insider_name=name,
                    role=_text(row.get("Position")),
                    transaction_type=kind,
                    transaction_date=at,
                    shares=_decimal(row.get("Shares")),
                    price=price,
                    value=_decimal(row.get("Value")),
                )
            )
        transactions.sort(key=lambda transaction: transaction.transaction_date, reverse=True)
        return ProviderInsiderData(
            symbol=normalize_symbol(symbol),
            provider=self.provider_name,
            transactions=transactions[:limit],
        )

    def fetch_holders(self, symbol: str) -> HoldersSnapshot:
        # One quoteSummary request fills every holder table of the ticker.
        frames = self._read(
            symbol,
            lambda ticker: (
                ticker.major_holders,
                ticker.institutional_holders,
                ticker.mutualfund_holders,
                ticker.insider_roster_holders,
            ),
        )
        breakdown, institutions, funds, insiders = frames
        return HoldersSnapshot(
            symbol=normalize_symbol(symbol),
            provider=self.provider_name,
            breakdown=_breakdown(breakdown),
            institutions=_positions(institutions),
            funds=_positions(funds),
            insiders=[
                InsiderHolding(
                    name=name,
                    position=_text(row.get("Position")),
                    latest_transaction=_text(row.get("Most Recent Transaction")),
                    latest_transaction_date=_day(row.get("Latest Transaction Date")),
                    shares_owned_directly=_count(row.get("Shares Owned Directly")),
                    position_direct_date=_day(row.get("Position Direct Date")),
                )
                for row in _records(insiders)
                if (name := _text(row.get("Name"))) is not None
            ],
        )

    def fetch_analyst_estimates(self, symbol: str) -> AnalystEstimatesSnapshot:
        eps, revenue, trend, revisions, targets, recommendations, history, ratings = self._read(
            symbol,
            lambda ticker: (
                ticker.earnings_estimate,
                ticker.revenue_estimate,
                ticker.eps_trend,
                ticker.eps_revisions,
                ticker.analyst_price_targets,
                ticker.recommendations,
                ticker.earnings_history,
                ticker.upgrades_downgrades,
            ),
        )
        return AnalystEstimatesSnapshot(
            symbol=normalize_symbol(symbol),
            provider=self.provider_name,
            periods=_periods(eps, revenue, trend, revisions),
            price_target=_price_target(targets),
            recommendations=[
                RecommendationCount(
                    period=period,
                    strong_buy=counts[0],
                    buy=counts[1],
                    hold=counts[2],
                    sell=counts[3],
                    strong_sell=counts[4],
                )
                for row in _records(recommendations)
                if (period := _text(row.get("period"))) is not None
                and None not in (counts := [_count(row.get(key)) for key in _RECOMMENDATIONS])
            ],
            earnings_history=sorted(
                (
                    EarningsSurprise(
                        quarter_end=quarter,
                        eps_actual=_decimal(row.get("epsActual")),
                        eps_estimate=_decimal(row.get("epsEstimate")),
                        eps_difference=_decimal(row.get("epsDifference")),
                        surprise_percent=_percent(row.get("surprisePercent")),
                    )
                    for label, row in _indexed(history)
                    if (quarter := _day(label)) is not None
                ),
                key=lambda item: item.quarter_end,
                reverse=True,
            ),
            rating_changes=sorted(
                (
                    RatingChange(
                        at=to_utc(at),
                        firm=firm,
                        to_grade=_text(row.get("ToGrade")),
                        from_grade=_text(row.get("FromGrade")),
                        action=_text(row.get("Action")),
                        price_target_action=_text(row.get("priceTargetAction")),
                        current_price_target=_target(row.get("currentPriceTarget")),
                        prior_price_target=_target(row.get("priorPriceTarget")),
                    )
                    for label, row in _indexed(ratings)
                    if (at := _moment(label)) is not None
                    and (firm := _text(row.get("Firm"))) is not None
                ),
                key=lambda item: item.at,
                reverse=True,
            ),
        )

    def _read(self, symbol: str, reader: Callable[[yf.Ticker], _T]) -> _T:
        try:
            return reader(self._ticker_factory(symbol))
        except Exception as exc:
            raise QuoteProviderError(f"Provider request failed for {symbol}") from exc

    def _history(
        self, symbol: str, *, interval: str, **window: object
    ) -> tuple[pd.DataFrame, Mapping[str, object]]:
        ticker = self._ticker_factory(symbol)
        try:
            frame = ticker.history(
                interval=interval,
                auto_adjust=False,
                actions=False,
                timeout=self.timeout,
                **window,
            )
            meta = ticker.get_history_metadata()
        except Exception as exc:
            raise QuoteProviderError(f"Quote request failed for {symbol}") from exc
        return frame, meta


def _bars(
    frame: pd.DataFrame, meta: Mapping[str, object], interval: str
) -> Iterator[tuple[datetime, Mapping[str, object]]]:
    """Yield bars at Yahoo's own labels.

    yfinance moves daily bars to exchange-local midnight, while Yahoo labels them at the
    regular session start; windows and research cutoffs compare against that start.
    Weekly and monthly bars already carry Yahoo's midnight labels.
    """
    opening = _session_opening(meta) if interval == "1d" else None
    for label, bar in frame.to_dict("index").items():
        at = _moment(label) if opening is None else datetime.combine(label.date(), opening)
        if at is not None:
            yield to_utc(at), bar


def _session_opening(meta: Mapping[str, object]) -> time | None:
    period = meta.get("currentTradingPeriod")
    regular = period.get("regular") if isinstance(period, Mapping) else None
    start = _moment(regular.get("start")) if isinstance(regular, Mapping) else None
    zone = meta.get("exchangeTimezoneName")
    if start is None or not isinstance(zone, str):
        return None
    local = start.astimezone(ZoneInfo(zone))
    return local.time().replace(tzinfo=local.tzinfo)


def _moment(value: object) -> datetime | None:
    # yfinance formats metadata times as pandas Timestamps; unformatted metadata keeps epochs.
    if isinstance(value, datetime):
        return datetime.fromtimestamp(value.timestamp(), tz=UTC)
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return Decimal(str(value))


def _volume(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return int(value)


def _name(meta: Mapping[str, object]) -> str | None:
    for key in ("longName", "shortName"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _currency(meta: Mapping[str, object]) -> str | None:
    currency = meta.get("currency")
    return normalize_currency(str(currency)) if currency is not None else None


def _records(frame: pd.DataFrame | None) -> list[dict]:
    return [] if frame is None or frame.empty else frame.to_dict("records")


def _indexed(frame: pd.DataFrame | None) -> list[tuple[object, dict]]:
    # Rating changes can share a timestamp, so rows are not keyed by their index.
    if frame is None or frame.empty:
        return []
    return list(zip(frame.index, frame.to_dict("records"), strict=True))


def _transaction(text: str | None) -> tuple[str, Decimal | None]:
    """Split Yahoo's row text, such as 'Sale at price 330.19 per share.'."""
    if text is None:
        return "Unspecified", None
    match = _TRANSACTION.fullmatch(text)
    if match is None:
        return text.rstrip("."), None
    # A price range has no single transaction price.
    return match["kind"], None if match["range"] else Decimal(match["price"])


def _breakdown(frame: pd.DataFrame | None) -> OwnershipBreakdown | None:
    if frame is None or frame.empty or "Value" not in frame.columns:
        return None
    values = {str(label): value for label, value in frame["Value"].to_dict().items()}
    return OwnershipBreakdown(
        insiders_percent=_percent(values.get("insidersPercentHeld")),
        institutions_percent=_percent(values.get("institutionsPercentHeld")),
        institutions_float_percent=_percent(values.get("institutionsFloatPercentHeld")),
        institution_count=_count(values.get("institutionsCount")),
    )


def _positions(frame: pd.DataFrame | None) -> list[HolderPosition]:
    return [
        HolderPosition(
            holder=holder,
            report_date=_day(row.get("Date Reported")),
            percent_held=_percent(row.get("pctHeld")),
            shares=_count(row.get("Shares")),
            value=_decimal(row.get("Value")),
            percent_change=_percent(row.get("pctChange")),
        )
        for row in _records(frame)
        if (holder := _text(row.get("Holder"))) is not None
    ]


def _periods(*frames: pd.DataFrame | None) -> list[EstimatePeriod]:
    """Join the EPS, revenue, EPS trend and revision tables on Yahoo's period label."""
    eps, revenue, trend, revisions = (
        {str(label): row for label, row in _indexed(frame)} for frame in frames
    )
    labels = dict.fromkeys([*eps, *revenue, *trend, *revisions])
    return [
        EstimatePeriod(
            period=label,
            eps=_estimate(eps.get(label), "yearAgoEps"),
            revenue=_estimate(revenue.get(label), "yearAgoRevenue"),
            eps_trend=(
                EpsTrend(
                    current=_decimal(row.get("current")),
                    seven_days_ago=_decimal(row.get("7daysAgo")),
                    thirty_days_ago=_decimal(row.get("30daysAgo")),
                    sixty_days_ago=_decimal(row.get("60daysAgo")),
                    ninety_days_ago=_decimal(row.get("90daysAgo")),
                )
                if (row := trend.get(label)) is not None
                else None
            ),
            eps_revisions=(
                EpsRevisions(
                    up_last7_days=_count(row.get("upLast7days")),
                    up_last30_days=_count(row.get("upLast30days")),
                    down_last7_days=_count(row.get("downLast7Days")),
                    down_last30_days=_count(row.get("downLast30days")),
                )
                if (row := revisions.get(label)) is not None
                else None
            ),
        )
        for label in labels
    ]


def _estimate(row: dict | None, year_ago: str) -> EstimateRange | None:
    if row is None:
        return None
    return EstimateRange(
        average=_decimal(row.get("avg")),
        low=_decimal(row.get("low")),
        high=_decimal(row.get("high")),
        year_ago=_decimal(row.get(year_ago)),
        analyst_count=_count(row.get("numberOfAnalysts")),
        growth_percent=_percent(row.get("growth")),
        currency=_text(row.get("currency")),
    )


def _price_target(values: object) -> PriceTarget | None:
    if not isinstance(values, Mapping):
        return None
    fields = {
        key: _decimal(values.get(key)) for key in ("current", "high", "low", "mean", "median")
    }
    return PriceTarget(**fields) if any(value is not None for value in fields.values()) else None


def _target(value: object) -> Decimal | None:
    # Yahoo reports an absent price target as 0.
    number = _decimal(value)
    return number if number is not None and number > 0 else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _day(value: object) -> date | None:
    # Holder, insider and earnings tables label rows with naive dates.
    return value.date() if isinstance(value, datetime) and not pd.isna(value) else None


def _count(value: object) -> int | None:
    number = _decimal(value)
    return None if number is None else int(number)


def _percent(value: object) -> Decimal | None:
    """Yahoo reports ownership, growth and surprises as fractions; the contract uses percent."""
    number = _decimal(value)
    if number is None:
        return None
    scaled = number.scaleb(2)
    # str(Decimal), which the wire model writes, would turn a positive exponent into 1E+2.
    return scaled.quantize(Decimal(1)) if scaled.as_tuple().exponent > 0 else scaled


__all__ = ["YahooFinanceQuoteProvider"]
