from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, cast

import httpx
from plugin_runtime.formatting import normalize_currency, normalize_symbol, to_utc


class QuoteProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: dict[str, str] = details or {}


class QuoteProviderMissingKeyError(QuoteProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_api_key_missing", details=details)


class QuoteProviderTimeoutError(QuoteProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_timeout", details=details)


class QuoteProviderRateLimitError(QuoteProviderError):
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message, code="provider_rate_limited", details=details)


@dataclass(slots=True)
class ProviderQuote:
    symbol: str
    price: Decimal
    previous_close: Decimal | None
    currency: str
    provider: str
    as_of: datetime | None
    name: str | None = None


@dataclass(slots=True)
class ProviderHistoryPoint:
    at: datetime
    close: Decimal


@dataclass(slots=True)
class ProviderHistorySeries:
    symbol: str
    currency: str | None
    provider: str
    points: list[ProviderHistoryPoint]


@dataclass(slots=True)
class ProviderOhlcvRow:
    at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = None
    adjusted_close: Decimal | None = None


@dataclass(slots=True)
class ProviderOhlcvSeries:
    symbol: str
    currency: str | None
    provider: str
    rows: list[ProviderOhlcvRow]


@dataclass(slots=True)
class ProviderFundamentalMetric:
    name: str
    value: Decimal | str | None
    currency: str | None = None
    period: str | None = None
    as_of: datetime | None = None


@dataclass(slots=True)
class ProviderFinancialStatementLine:
    name: str
    value: Decimal | None
    currency: str | None = None


@dataclass(slots=True)
class ProviderFinancialStatement:
    statement_type: Literal["income_statement", "balance_sheet", "cash_flow"]
    period: Literal["annual", "quarterly", "trailing_twelve_months"]
    period_end: datetime
    lines: list[ProviderFinancialStatementLine]


@dataclass(slots=True)
class ProviderFundamentals:
    symbol: str
    provider: str
    as_of: datetime
    metrics: list[ProviderFundamentalMetric]
    statements: list[ProviderFinancialStatement]


@dataclass(slots=True)
class ProviderInsiderTransaction:
    insider_name: str
    transaction_type: str
    transaction_date: datetime
    role: str | None = None
    shares: Decimal | None = None
    price: Decimal | None = None
    value: Decimal | None = None
    filed_at: datetime | None = None


@dataclass(slots=True)
class ProviderInsiderData:
    symbol: str
    provider: str
    transactions: list[ProviderInsiderTransaction]


class QuoteProvider(Protocol):
    def fetch_symbol_name(self, symbol: str) -> str | None: ...

    def fetch_quote(self, symbol: str) -> ProviderQuote: ...

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries: ...

    def fetch_ohlcv(
        self, symbol: str, *, start_date: datetime, end_date: datetime, interval: str
    ) -> ProviderOhlcvSeries: ...

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals: ...

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData: ...


class YahooFinanceQuoteProvider:
    provider_name: str = "yahoo_finance"

    def __init__(self, timeout: float) -> None:
        self.timeout: float = timeout

    def fetch_symbol_name(self, symbol: str) -> str | None:
        meta = self._fetch_chart_meta(symbol, interval="1d", range_value="1d")
        return _coerce_name(meta.get("longName")) or _coerce_name(meta.get("shortName"))

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        meta = self._fetch_chart_meta(symbol, interval="1d", range_value="1d")
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        currency = meta.get("currency")
        name = _coerce_name(meta.get("longName")) or _coerce_name(meta.get("shortName"))
        if price is None or currency is None:
            raise QuoteProviderError(f"Quote payload was incomplete for {symbol}")

        market_time = _coerce_timestamp(meta.get("regularMarketTime"))
        as_of = datetime.fromtimestamp(market_time, tz=UTC) if market_time is not None else None

        return ProviderQuote(
            symbol=normalize_symbol(symbol),
            name=name,
            price=Decimal(str(price)),
            previous_close=(Decimal(str(previous_close)) if previous_close is not None else None),
            currency=normalize_currency(str(currency)),
            provider=self.provider_name,
            as_of=as_of,
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        result = self._fetch_chart_result(symbol, interval=interval, range_value=range_value)
        meta = _as_object_dict(
            result.get("meta", {}), context=f"Historical quote meta for {symbol}"
        )
        indicators = _as_object_dict(
            result.get("indicators", {}),
            context=f"Historical quote indicators for {symbol}",
        )
        indicator_items = _as_object_list(
            indicators.get("quote", []),
            context=f"Historical quote indicator items for {symbol}",
        )
        quote_items = (
            _as_object_dict(indicator_items[0], context=f"Historical quote items for {symbol}")
            if indicator_items
            else {}
        )
        closes = _as_object_list(
            quote_items.get("close", []),
            context=f"Historical close series for {symbol}",
        )
        timestamps = _as_object_list(
            result.get("timestamp", []),
            context=f"Historical timestamps for {symbol}",
        )
        currency = meta.get("currency")

        points: list[ProviderHistoryPoint] = []
        for timestamp_value, close in zip(timestamps, closes, strict=False):
            timestamp = _coerce_timestamp(timestamp_value)
            if timestamp is None or close is None:
                continue

            points.append(
                ProviderHistoryPoint(
                    at=datetime.fromtimestamp(timestamp, tz=UTC),
                    close=Decimal(str(close)),
                )
            )

        if not points:
            raise QuoteProviderError(f"Historical quote payload was empty for {symbol}")

        return ProviderHistorySeries(
            symbol=normalize_symbol(symbol),
            currency=(normalize_currency(str(currency)) if currency is not None else None),
            provider=self.provider_name,
            points=points,
        )

    def fetch_ohlcv(
        self, symbol: str, *, start_date: datetime, end_date: datetime, interval: str
    ) -> ProviderOhlcvSeries:
        result = self._fetch_chart_result(
            symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        meta = _as_object_dict(result.get("meta", {}), context=f"OHLCV meta for {symbol}")
        indicators = _as_object_dict(
            result.get("indicators", {}),
            context=f"OHLCV indicators for {symbol}",
        )
        indicator_items = _as_object_list(
            indicators.get("quote", []),
            context=f"OHLCV quote indicator items for {symbol}",
        )
        quote_items = (
            _as_object_dict(indicator_items[0], context=f"OHLCV quote items for {symbol}")
            if indicator_items
            else {}
        )
        adjclose_items = _as_object_list(
            indicators.get("adjclose", []),
            context=f"OHLCV adjusted-close indicator items for {symbol}",
        )
        adjusted_close_items = (
            _as_object_list(
                _as_object_dict(
                    adjclose_items[0],
                    context=f"OHLCV adjusted-close items for {symbol}",
                ).get("adjclose", []),
                context=f"OHLCV adjusted-close series for {symbol}",
            )
            if adjclose_items
            else []
        )
        timestamps = _as_object_list(
            result.get("timestamp", []),
            context=f"OHLCV timestamps for {symbol}",
        )
        opens = _as_object_list(
            quote_items.get("open", []), context=f"OHLCV open series for {symbol}"
        )
        highs = _as_object_list(
            quote_items.get("high", []), context=f"OHLCV high series for {symbol}"
        )
        lows = _as_object_list(quote_items.get("low", []), context=f"OHLCV low series for {symbol}")
        closes = _as_object_list(
            quote_items.get("close", []), context=f"OHLCV close series for {symbol}"
        )
        volumes = _as_object_list(
            quote_items.get("volume", []), context=f"OHLCV volume series for {symbol}"
        )
        currency = meta.get("currency")

        rows: list[ProviderOhlcvRow] = []
        for index, timestamp_value in enumerate(timestamps):
            timestamp = _coerce_timestamp(timestamp_value)
            open_price = _coerce_decimal(_list_item(opens, index))
            high_price = _coerce_decimal(_list_item(highs, index))
            low_price = _coerce_decimal(_list_item(lows, index))
            close_price = _coerce_decimal(_list_item(closes, index))
            if (
                timestamp is None
                or open_price is None
                or high_price is None
                or low_price is None
                or close_price is None
            ):
                continue

            rows.append(
                ProviderOhlcvRow(
                    at=datetime.fromtimestamp(timestamp, tz=UTC),
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=_coerce_volume(_list_item(volumes, index)),
                    adjusted_close=_coerce_decimal(_list_item(adjusted_close_items, index)),
                )
            )

        if not rows:
            raise QuoteProviderError(f"OHLCV payload was empty for {symbol}")

        return ProviderOhlcvSeries(
            symbol=normalize_symbol(symbol),
            currency=(normalize_currency(str(currency)) if currency is not None else None),
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

    def _fetch_chart_meta(
        self, symbol: str, *, interval: str, range_value: str
    ) -> dict[str, object]:
        result = self._fetch_chart_result(symbol, interval=interval, range_value=range_value)
        return _as_object_dict(
            result.get("meta", {}),
            context=f"Quote metadata for {symbol}",
        )

    def _fetch_chart_result(
        self,
        symbol: str,
        *,
        interval: str,
        range_value: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, object]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params: dict[str, str | int] = {"interval": interval}
        if range_value is not None:
            params["range"] = range_value
        elif start_date is not None and end_date is not None:
            params["period1"] = int(to_utc(start_date).timestamp())
            params["period2"] = int(to_utc(end_date).timestamp()) + 1
        else:
            raise QuoteProviderError(f"Quote request bounds were incomplete for {symbol}")
        headers = {"User-Agent": "signaldeck-backend/0.1"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=headers)
                _ = response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QuoteProviderError(f"Quote request failed for {symbol}") from exc

        payload = _as_object_dict(
            cast(object, response.json()), context=f"Quote payload for {symbol}"
        )
        chart = _as_object_dict(payload.get("chart", {}), context=f"Quote payload for {symbol}")
        result_items = _as_object_list(
            chart.get("result", []),
            context=f"Quote result list for {symbol}",
        )
        if not result_items:
            raise QuoteProviderError(f"Quote payload was empty for {symbol}")

        return _as_object_dict(result_items[0], context=f"Quote result item for {symbol}")


class DeterministicQuoteProvider:
    provider_name: str = "deterministic_test"

    def __init__(self, *, anchor_date: date | None = None) -> None:
        self.anchor_date: date = anchor_date or date(2024, 1, 1)

    def fetch_symbol_name(self, symbol: str) -> str | None:
        names = {
            "AAPL": "Apple Inc.",
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ Composite",
            "^DJI": "Dow Jones Industrial Average",
        }
        return names.get(normalize_symbol(symbol), normalize_symbol(symbol))

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        current_date = date(2024, 3, 29)
        close = self._price_for_day(symbol, current_date) + Decimal("0.5")
        return ProviderQuote(
            symbol=normalize_symbol(symbol),
            price=close,
            previous_close=close - Decimal("0.5"),
            currency="USD",
            provider=self.provider_name,
            as_of=datetime.combine(current_date, datetime.min.time(), tzinfo=UTC),
            name=self.fetch_symbol_name(symbol),
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        _ = (range_value, interval)
        points = [
            ProviderHistoryPoint(
                at=datetime.combine(point_date, datetime.min.time(), tzinfo=UTC),
                close=self._price_for_day(symbol, point_date) + Decimal("0.5"),
            )
            for point_date in self._iter_days(date(2024, 1, 2), date(2024, 3, 29))
        ]
        return ProviderHistorySeries(
            symbol=normalize_symbol(symbol),
            currency="USD",
            provider=self.provider_name,
            points=points,
        )

    def fetch_ohlcv(
        self, symbol: str, *, start_date: datetime, end_date: datetime, interval: str
    ) -> ProviderOhlcvSeries:
        _ = interval
        rows: list[ProviderOhlcvRow] = []
        for point_date in self._iter_days(to_utc(start_date).date(), to_utc(end_date).date()):
            open_price = self._price_for_day(symbol, point_date)
            close_price = open_price + Decimal("0.5")
            rows.append(
                ProviderOhlcvRow(
                    at=datetime.combine(point_date, datetime.min.time(), tzinfo=UTC),
                    open=open_price,
                    high=open_price + Decimal("1.0"),
                    low=open_price - Decimal("1.0"),
                    close=close_price,
                    volume=1_000_000 + (point_date - self.anchor_date).days * 100,
                    adjusted_close=close_price - Decimal("0.05"),
                )
            )

        return ProviderOhlcvSeries(
            symbol=normalize_symbol(symbol),
            currency="USD",
            provider=self.provider_name,
            rows=rows,
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        normalized_symbol = normalize_symbol(symbol)
        as_of = datetime.combine(date(2024, 3, 29), datetime.min.time(), tzinfo=UTC)
        return ProviderFundamentals(
            symbol=normalized_symbol,
            provider=self.provider_name,
            as_of=as_of,
            metrics=[
                ProviderFundamentalMetric(
                    name="market_cap",
                    value=Decimal("1000000000"),
                    currency="USD",
                    period="ttm",
                    as_of=as_of,
                ),
                ProviderFundamentalMetric(
                    name="enterprise_value",
                    value=Decimal("1200000000"),
                    currency="USD",
                    period="ttm",
                    as_of=as_of,
                ),
                ProviderFundamentalMetric(
                    name="trailing_pe", value=Decimal("28.5"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="price_to_sales", value=Decimal("9.4"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="gross_margin", value=Decimal("0.62"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="operating_margin", value=Decimal("0.31"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="net_margin", value=Decimal("0.24"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="return_on_equity", value=Decimal("0.34"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="revenue_growth", value=Decimal("0.18"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="earnings_growth", value=Decimal("0.21"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="free_cash_flow_margin", value=Decimal("0.19"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="debt_to_equity", value=Decimal("0.42"), period="mrq", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="current_ratio", value=Decimal("1.80"), period="mrq", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="dividend_yield", value=Decimal("0.006"), period="ttm", as_of=as_of
                ),
                ProviderFundamentalMetric(
                    name="beta", value=Decimal("1.20"), period="5y", as_of=as_of
                ),
            ],
            statements=[
                ProviderFinancialStatement(
                    statement_type="income_statement",
                    period="annual",
                    period_end=as_of,
                    lines=[
                        ProviderFinancialStatementLine(
                            name="revenue",
                            value=Decimal("100000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="gross_profit",
                            value=Decimal("62000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="operating_income",
                            value=Decimal("31000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="ebitda",
                            value=Decimal("36000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="net_income",
                            value=Decimal("24000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="eps_diluted",
                            value=Decimal("4.20"),
                            currency="USD",
                        ),
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="balance_sheet",
                    period="annual",
                    period_end=as_of,
                    lines=[
                        ProviderFinancialStatementLine(
                            name="cash_and_equivalents",
                            value=Decimal("12000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="total_assets",
                            value=Decimal("240000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="total_liabilities",
                            value=Decimal("96000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="total_debt",
                            value=Decimal("42000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="total_equity",
                            value=Decimal("144000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="shares_outstanding",
                            value=Decimal("10000000"),
                        ),
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="cash_flow",
                    period="annual",
                    period_end=as_of,
                    lines=[
                        ProviderFinancialStatementLine(
                            name="operating_cash_flow",
                            value=Decimal("28000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="capital_expenditures",
                            value=Decimal("-9000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="free_cash_flow",
                            value=Decimal("19000000"),
                            currency="USD",
                        ),
                        ProviderFinancialStatementLine(
                            name="dividends_paid",
                            value=Decimal("-1200000"),
                            currency="USD",
                        ),
                    ],
                ),
            ],
        )

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        del start_date, end_date
        normalized_symbol = normalize_symbol(symbol)
        transaction_date = datetime.combine(date(2024, 3, 29), datetime.min.time(), tzinfo=UTC)
        return ProviderInsiderData(
            symbol=normalized_symbol,
            provider=self.provider_name,
            transactions=[
                ProviderInsiderTransaction(
                    insider_name="Deterministic Insider",
                    role="Director",
                    transaction_type="BUY",
                    shares=Decimal("10"),
                    price=Decimal("100"),
                    value=Decimal("1000"),
                    filed_at=transaction_date,
                    transaction_date=transaction_date,
                )
            ][:limit],
        )

    def download_history(self, symbol: str, start: date, end: date) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for point_date in self._iter_days(start, end):
            open_price = self._price_for_day(symbol, point_date)
            rows.append(
                {
                    "date": point_date.isoformat(),
                    "open": float(open_price),
                    "high": float(open_price + Decimal("1.0")),
                    "low": float(open_price - Decimal("1.0")),
                    "close": float(open_price + Decimal("0.5")),
                    "volume": 1_000_000 + (point_date - self.anchor_date).days * 100,
                }
            )
        return rows

    def _iter_days(self, start: date, end: date) -> list[date]:
        current = start
        days: list[date] = []
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days

    def _price_for_day(self, symbol: str, point_date: date) -> Decimal:
        base_prices = {
            "AAPL": Decimal("180.0"),
            "^GSPC": Decimal("4700.0"),
            "^IXIC": Decimal("16000.0"),
            "^DJI": Decimal("38000.0"),
        }
        base = base_prices.get(normalize_symbol(symbol), Decimal("100.0"))
        offset = Decimal((point_date - self.anchor_date).days) / Decimal("10")
        return base + offset


def _as_object_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QuoteProviderError(f"{context} was malformed")

    return cast(dict[str, object], value)


def _as_object_list(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise QuoteProviderError(f"{context} was malformed")

    return cast(list[object], value)


def _list_item(items: list[object], index: int) -> object:
    if index >= len(items):
        return None
    return items[index]


def _coerce_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    name = value.strip()
    return name or None


def _coerce_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _coerce_volume(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_timestamp(value: object) -> int | None:
    if isinstance(value, int | float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None

    return None
