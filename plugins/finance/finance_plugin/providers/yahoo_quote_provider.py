"""Yahoo Finance quotes, history and daily bars read through yfinance."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from plugin_runtime.formatting import normalize_currency, normalize_symbol, to_utc

from .quote_provider import (
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)

# Raise provider failures instead of letting yfinance log them and return empty frames.
yf.config.debug.hide_exceptions = False

_PRICE_COLUMNS = ("Open", "High", "Low", "Close")


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
        del start_date, end_date, limit
        raise QuoteProviderError(
            f"Insider transactions are unavailable for {normalize_symbol(symbol)}",
            code="provider_unavailable",
            details={"provider": self.provider_name, "symbol": normalize_symbol(symbol)},
        )

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


__all__ = ["YahooFinanceQuoteProvider"]
