from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, TypeVar, cast

from finance_plugin.constants import DEFAULT_CURRENCY
from finance_plugin.contracts import RuntimeToolWarning
from finance_plugin.models.market_quote import MarketQuote
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFinancialStatement as RuntimeFinancialStatement,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFinancialStatementLine as RuntimeFinancialStatementLine,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFundamentalMetric as RuntimeFundamentalMetric,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataFundamentalsLookupResult as RuntimeFundamentalsLookupResult,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataIndicatorLookupResult as RuntimeIndicatorLookupResult,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataIndicatorRow as RuntimeIndicatorRow,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataIndicatorValue as RuntimeIndicatorValue,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataInsiderDataLookupResult as RuntimeInsiderDataLookupResult,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataInsiderTransaction as RuntimeInsiderTransaction,
)
from finance_plugin.providers.market_data_snapshots import MarketDataNewsItem as RuntimeNewsItem
from finance_plugin.providers.market_data_snapshots import (
    MarketDataNewsLookupResult as RuntimeNewsLookupResult,
)
from finance_plugin.providers.market_data_snapshots import (
    MarketDataOhlcvLookupResult as RuntimeOhlcvLookupResult,
)
from finance_plugin.providers.market_data_snapshots import MarketDataOhlcvRow as RuntimeOhlcvRow
from finance_plugin.providers.market_data_snapshots import (
    MarketDataOhlcvSeries as RuntimeOhlcvSeries,
)
from finance_plugin.providers.news_provider import (
    NewsProvider,
    NewsProviderError,
    NewsScope,
    ProviderNewsItem,
    ProviderNewsResult,
)
from finance_plugin.providers.quote_provider import (
    ProviderFinancialStatement,
    ProviderFinancialStatementLine,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProvider,
    QuoteProviderError,
)
from finance_plugin.repositories.market_quote import MarketQuoteRepository
from finance_plugin.schemas.market_data import (
    MarketHistoryPointRead,
    MarketHistoryRead,
    MarketHistorySeriesRead,
    MarketQuoteListRead,
    MarketQuoteRead,
)
from plugin_runtime.common import to_camel
from plugin_runtime.formatting import normalize_symbol, to_utc, utcnow
from sqlalchemy.orm import Session

_ProviderResultT = TypeVar("_ProviderResultT")
_ProviderT = TypeVar("_ProviderT", QuoteProvider, NewsProvider)

_FUNDAMENTAL_METRIC_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "market_cap",
            "enterprise_value",
            "trailing_pe",
            "forward_pe",
            "price_to_sales",
            "price_to_book",
            "ev_to_ebitda",
            "gross_margin",
            "operating_margin",
            "net_margin",
            "return_on_equity",
            "return_on_assets",
            "revenue_growth",
            "earnings_growth",
            "free_cash_flow_margin",
            "debt_to_equity",
            "current_ratio",
            "dividend_yield",
            "beta",
        )
    )
}
_FINANCIAL_STATEMENT_TYPE_ORDER = {
    "income_statement": 0,
    "balance_sheet": 1,
    "cash_flow": 2,
}
_FINANCIAL_STATEMENT_PERIOD_ORDER = {
    "annual": 0,
    "quarterly": 1,
    "trailing_twelve_months": 2,
}
_FINANCIAL_STATEMENT_LINE_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "revenue",
            "gross_profit",
            "operating_income",
            "ebitda",
            "net_income",
            "eps_diluted",
            "cash_and_equivalents",
            "total_assets",
            "total_liabilities",
            "total_debt",
            "total_equity",
            "shares_outstanding",
            "operating_cash_flow",
            "capital_expenditures",
            "free_cash_flow",
            "dividends_paid",
        )
    )
}


@dataclass(frozen=True, slots=True)
class MarketClosePoint:
    at: datetime
    close: Decimal


@dataclass(frozen=True, slots=True)
class MarketIndicatorSelection:
    indicator: str
    window: int | None = None
    fast_window: int | None = None
    slow_window: int | None = None
    signal_window: int | None = None
    standard_deviations: Decimal | None = None


_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_ -]?key|token|secret|password|credential)(\s*[=:]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9][A-Za-z0-9_-]*")
_SENSITIVE_WARNING_DETAIL_KEY_RE = re.compile(
    r"api[_-]?key|authorization|bearer|credential|password|secret|token",
    re.IGNORECASE,
)
_WARNING_DETAIL_KEY_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")

__all__ = [
    "MarketClosePoint",
    "MarketDataService",
    "MarketIndicatorSelection",
    "ProviderFinancialStatement",
    "ProviderFundamentalMetric",
    "ProviderFundamentals",
    "ProviderHistoryPoint",
    "ProviderHistorySeries",
    "ProviderInsiderData",
    "ProviderInsiderTransaction",
    "ProviderNewsItem",
    "ProviderNewsResult",
    "ProviderOhlcvRow",
    "ProviderOhlcvSeries",
    "ProviderQuote",
    "QuoteProvider",
    "QuoteProviderError",
]


class MarketDataService:
    history_interval_by_range: dict[str, str] = {
        "1mo": "1d",
        "3mo": "1d",
        "ytd": "1wk",
        "1y": "1wk",
        "max": "1mo",
    }
    ohlcv_interval: str = "1d"
    ohlcv_default_row_limit: int = 250
    ohlcv_max_row_limit: int = 500
    provider_fallback_max_attempts: int = 3
    news_default_item_limit: int = 25
    news_max_item_limit: int = 50
    insider_default_transaction_limit: int = 50
    insider_max_transaction_limit: int = 100

    def __init__(
        self,
        session: Session,
        quote_provider: QuoteProvider,
        news_providers: Sequence[NewsProvider] | None = None,
        quote_stale_after_minutes: int = 15,
    ) -> None:
        self.session: Session = session
        self.quote_provider: QuoteProvider = quote_provider
        self.news_providers: tuple[NewsProvider, ...] = tuple(news_providers or ())
        self.repository: MarketQuoteRepository = MarketQuoteRepository(session)
        self.quote_stale_after_minutes: int = quote_stale_after_minutes

    def get_quotes(self, symbols: list[str]) -> MarketQuoteListRead:
        quotes: list[MarketQuoteRead] = []
        warnings: list[str] = []
        updated_cache = False

        seen_symbols: set[str] = set()
        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)

            quote, warning, was_updated = self._resolve_quote(symbol)
            if quote is not None:
                quotes.append(quote)
            if warning is not None:
                warnings.append(warning)
            updated_cache = updated_cache or was_updated

        if updated_cache:
            self.session.commit()

        return MarketQuoteListRead(quotes=quotes, warnings=warnings)

    def get_history(self, symbols: list[str], range_value: str) -> MarketHistoryRead:
        return self._build_history_read(symbols, range_value)

    def get_quote_snapshot(self, symbol: str) -> tuple[MarketQuoteRead | None, list[str]]:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            return None, ["Symbol is required"]
        quote, warning, was_updated = self._resolve_quote(normalized_symbol)
        if was_updated:
            self.session.commit()
        return quote, ([warning] if warning is not None else [])

    def get_history_snapshot(self, symbol: str, range_value: str) -> MarketHistoryRead:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")
        return self._build_history_read([normalized_symbol], range_value)

    def get_close_history_snapshot(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MarketClosePoint]:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")

        provider_series = self.quote_provider.fetch_ohlcv(
            normalized_symbol,
            start_date=normalized_start,
            end_date=normalized_end,
            interval=self.ohlcv_interval,
        )
        return self._build_close_history_points(
            provider_series.rows,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    def get_ohlcv_snapshot(
        self,
        symbols: list[str],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int | None = None,
    ) -> RuntimeOhlcvLookupResult:
        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")

        effective_row_limit = self._normalize_ohlcv_row_limit(row_limit)
        seen_symbols: set[str] = set()
        series: list[RuntimeOhlcvSeries] = []
        warnings: list[RuntimeToolWarning] = []

        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue

            seen_symbols.add(symbol)

            try:
                provider_series = self.quote_provider.fetch_ohlcv(
                    symbol,
                    start_date=normalized_start,
                    end_date=normalized_end,
                    interval=self.ohlcv_interval,
                )
            except QuoteProviderError:
                warnings.append(
                    RuntimeToolWarning(
                        code="ohlcv_unavailable",
                        message=f"No OHLCV data available for {symbol}",
                        details={"symbol": symbol},
                    )
                )
                continue

            rows = self._build_ohlcv_rows(
                provider_series.rows,
                start_date=normalized_start,
                end_date=normalized_end,
                row_limit=effective_row_limit,
            )
            if not rows:
                warnings.append(
                    RuntimeToolWarning(
                        code="ohlcv_unavailable",
                        message=f"No OHLCV data available for {symbol}",
                        details={"symbol": symbol},
                    )
                )
                continue

            series.append(
                RuntimeOhlcvSeries(
                    symbol=normalize_symbol(provider_series.symbol),
                    currency=provider_series.currency,
                    provider=provider_series.provider,
                    rows=rows,
                )
            )

        return RuntimeOhlcvLookupResult(
            start_date=normalized_start,
            end_date=normalized_end,
            series=series,
            warnings=warnings,
        )

    def get_indicator_snapshot(
        self,
        symbol: str,
        *,
        current_date: datetime,
        start_date: datetime,
        end_date: datetime,
        indicators: Sequence[MarketIndicatorSelection],
        row_limit: int | None = None,
    ) -> RuntimeIndicatorLookupResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        normalized_current = to_utc(current_date)
        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")
        if normalized_end > normalized_current:
            raise QuoteProviderError("endDate cannot be after currentDate")

        normalized_indicators = self._normalize_indicator_selections(indicators)
        ohlcv_result = self.get_ohlcv_snapshot(
            [normalized_symbol],
            start_date=normalized_start,
            end_date=normalized_end,
            row_limit=row_limit,
        )
        if not ohlcv_result.series:
            return RuntimeIndicatorLookupResult(
                symbol=normalized_symbol,
                provider=str(getattr(self.quote_provider, "provider_name", "")),
                current_date=normalized_current,
                start_date=normalized_start,
                end_date=normalized_end,
                rows=[],
                warnings=ohlcv_result.warnings,
            )

        ohlcv_series = ohlcv_result.series[0]
        return RuntimeIndicatorLookupResult(
            symbol=ohlcv_series.symbol,
            provider=ohlcv_series.provider,
            current_date=normalized_current,
            start_date=normalized_start,
            end_date=normalized_end,
            rows=self._build_indicator_rows(
                ohlcv_series.rows,
                current_date=normalized_current,
                indicators=normalized_indicators,
            ),
            warnings=ohlcv_result.warnings,
        )

    def get_fundamentals_snapshot(
        self,
        symbol: str,
        *,
        providers: Sequence[QuoteProvider] | None = None,
    ) -> RuntimeFundamentalsLookupResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            default_providers=(self.quote_provider,),
            operation="fundamentals",
            call=lambda provider: provider.fetch_fundamentals(normalized_symbol),
        )
        if provider_result is None:
            return RuntimeFundamentalsLookupResult(
                symbol=normalized_symbol,
                provider="",
                as_of=utcnow(),
                metrics=[],
                statements=[],
                warnings=warnings,
            )

        metrics = self._build_fundamental_metrics(provider_result.metrics)
        statements = [
            RuntimeFinancialStatement(
                statement_type=statement.statement_type,
                period=statement.period,
                period_end=to_utc(statement.period_end),
                lines=[
                    RuntimeFinancialStatementLine(
                        name=line.name,
                        value=line.value,
                        currency=line.currency,
                    )
                    for line in self._sort_fundamental_statement_lines(statement.lines)
                ],
            )
            for statement in self._sort_fundamental_statements(provider_result.statements)
        ]
        if not metrics and not statements:
            warnings.append(
                self._runtime_warning(
                    code="fundamentals_empty",
                    message=f"No fundamentals returned for {normalized_symbol}",
                    details={"symbol": normalized_symbol, "provider": provider_result.provider},
                )
            )
        return RuntimeFundamentalsLookupResult(
            symbol=normalize_symbol(provider_result.symbol),
            provider=provider_result.provider,
            as_of=to_utc(provider_result.as_of),
            metrics=metrics,
            statements=statements,
            warnings=warnings,
        )

    def get_news_snapshot(
        self,
        *,
        symbols: list[str] | None = None,
        query: str | None = None,
        scope: NewsScope | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        item_limit: int | None = None,
        providers: Sequence[NewsProvider] | None = None,
    ) -> RuntimeNewsLookupResult:
        normalized_symbols = self._normalize_optional_symbols(symbols or [])
        normalized_query = query.strip() if query is not None and query.strip() else None
        normalized_scope = self._normalize_news_scope(
            scope,
            symbols=normalized_symbols,
        )
        normalized_start = to_utc(start_date) if start_date is not None else None
        normalized_end = to_utc(end_date) if end_date is not None else None
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise QuoteProviderError("startDate must be before or equal to endDate")
        effective_limit = self._normalize_result_limit(
            item_limit,
            default_limit=self.news_default_item_limit,
            max_limit=self.news_max_item_limit,
            label="News itemLimit",
        )

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            default_providers=self.news_providers,
            operation="news",
            call=lambda provider: provider.fetch_news(
                symbols=normalized_symbols,
                query=normalized_query,
                scope=normalized_scope,
                start_date=normalized_start,
                end_date=normalized_end,
                limit=effective_limit + 1,
            ),
        )
        items = self._build_news_items(
            provider_result.items if provider_result is not None else [],
            start_date=normalized_start,
            end_date=normalized_end,
        )
        if len(items) > effective_limit:
            items = items[:effective_limit]
            warnings.append(
                self._runtime_warning(
                    code="news_truncated",
                    message=f"News results were truncated to {effective_limit} items",
                    details={"limit": str(effective_limit), "scope": normalized_scope},
                )
            )
        if provider_result is not None and normalized_scope == "global":
            warnings.append(
                self._runtime_warning(
                    code="news_global_coverage_limited",
                    message="Global news coverage is bounded by the configured finance provider",
                    details={
                        "scope": normalized_scope,
                        "provider": provider_result.provider,
                    },
                )
            )
        if provider_result is not None and not items:
            warnings.append(
                self._runtime_warning(
                    code="news_empty",
                    message="No news returned for the request",
                    details={
                        "symbols": ",".join(normalized_symbols),
                        "query": normalized_query or "",
                        "scope": normalized_scope,
                        "provider": provider_result.provider,
                    },
                )
            )
        return RuntimeNewsLookupResult(
            query=normalized_query,
            symbols=normalized_symbols,
            start_date=normalized_start,
            end_date=normalized_end,
            items=items,
            warnings=warnings,
        )

    def get_insider_transactions_snapshot(
        self,
        symbol: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        transaction_limit: int | None = None,
        providers: Sequence[QuoteProvider] | None = None,
    ) -> RuntimeInsiderDataLookupResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")
        normalized_start = to_utc(start_date) if start_date is not None else None
        normalized_end = to_utc(end_date) if end_date is not None else None
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise QuoteProviderError("startDate must be before or equal to endDate")
        effective_limit = self._normalize_result_limit(
            transaction_limit,
            default_limit=self.insider_default_transaction_limit,
            max_limit=self.insider_max_transaction_limit,
            label="Insider transactionLimit",
        )

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            default_providers=(self.quote_provider,),
            operation="insider",
            call=lambda provider: provider.fetch_insider_transactions(
                normalized_symbol,
                start_date=normalized_start,
                end_date=normalized_end,
                limit=effective_limit + 1,
            ),
        )
        transactions = self._build_insider_transactions(
            provider_result.transactions if provider_result is not None else []
        )
        if len(transactions) > effective_limit:
            transactions = transactions[:effective_limit]
            warnings.append(
                self._runtime_warning(
                    code="insider_truncated",
                    message=f"Insider transactions were truncated to {effective_limit} rows",
                    details={"limit": str(effective_limit), "symbol": normalized_symbol},
                )
            )
        if provider_result is not None and not transactions:
            warnings.append(
                self._runtime_warning(
                    code="insider_empty",
                    message=f"No insider transactions returned for {normalized_symbol}",
                    details={"symbol": normalized_symbol, "provider": provider_result.provider},
                )
            )
        return RuntimeInsiderDataLookupResult(
            symbol=(
                normalize_symbol(provider_result.symbol)
                if provider_result is not None
                else normalized_symbol
            ),
            provider=provider_result.provider if provider_result is not None else "",
            start_date=normalized_start,
            end_date=normalized_end,
            transactions=transactions,
            warnings=warnings,
        )

    def _build_history_read(self, symbols: list[str], range_value: str) -> MarketHistoryRead:
        interval = self.history_interval_by_range.get(range_value)
        if interval is None:
            raise QuoteProviderError(f"Unsupported history range {range_value}")

        seen_symbols: set[str] = set()
        series: list[MarketHistorySeriesRead] = []
        warnings: list[str] = []

        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue

            seen_symbols.add(symbol)

            try:
                provider_series = self.quote_provider.fetch_history(
                    symbol, range_value=range_value, interval=interval
                )
            except QuoteProviderError:
                warnings.append(f"No history available for {symbol}")
                continue

            series.append(
                MarketHistorySeriesRead(
                    symbol=provider_series.symbol,
                    currency=provider_series.currency,
                    provider=provider_series.provider,
                    points=[
                        MarketHistoryPointRead(at=point.at, close=point.close)
                        for point in provider_series.points
                    ],
                )
            )

        return MarketHistoryRead(
            range=range_value,
            interval=interval,
            series=series,
            warnings=warnings,
        )

    def _build_close_history_points(
        self,
        rows: list[ProviderOhlcvRow],
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MarketClosePoint]:
        points: list[MarketClosePoint] = []
        for row in rows:
            row_time = to_utc(row.at)
            if start_date <= row_time <= end_date:
                points.append(MarketClosePoint(at=row_time, close=row.close))

        points.sort(key=lambda point: point.at)
        return points

    def _build_ohlcv_rows(
        self,
        rows: list[ProviderOhlcvRow],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int,
    ) -> list[RuntimeOhlcvRow]:
        normalized_rows: list[tuple[datetime, ProviderOhlcvRow]] = []
        for row in rows:
            row_time = to_utc(row.at)
            if start_date <= row_time <= end_date:
                normalized_rows.append((row_time, row))

        normalized_rows.sort(key=lambda item: item[0])
        selected_rows = normalized_rows[-row_limit:]
        return [
            RuntimeOhlcvRow(
                at=row_time,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=Decimal(row.volume) if row.volume is not None else None,
                adjusted_close=row.adjusted_close,
            )
            for row_time, row in selected_rows
        ]

    def _build_indicator_rows(
        self,
        rows: list[RuntimeOhlcvRow],
        *,
        current_date: datetime,
        indicators: tuple[MarketIndicatorSelection, ...],
    ) -> list[RuntimeIndicatorRow]:
        closes = [row.close for row in rows]
        computed = self._compute_indicator_series(rows, indicators)
        indicator_rows: list[RuntimeIndicatorRow] = []
        for row_index, row in enumerate(rows):
            row_time = to_utc(row.at)
            if row_time > current_date:
                raise QuoteProviderError("Indicator OHLCV rows cannot be after currentDate")

            values = [RuntimeIndicatorValue(name="close", value=row.close)]
            for indicator in indicators:
                values.extend(
                    self._indicator_values_for_row(
                        indicator,
                        row_index=row_index,
                        row_count=len(closes),
                        computed=computed,
                    )
                )

            indicator_rows.append(RuntimeIndicatorRow(at=row_time, values=values))

        return indicator_rows

    def _compute_indicator_series(
        self,
        rows: list[RuntimeOhlcvRow],
        indicators: tuple[MarketIndicatorSelection, ...],
    ) -> dict[tuple[object, ...], list[Decimal | None] | dict[str, list[Decimal | None]]]:
        closes = [row.close for row in rows]
        computed: dict[
            tuple[object, ...], list[Decimal | None] | dict[str, list[Decimal | None]]
        ] = {}
        for indicator in indicators:
            key = self._indicator_selection_key(indicator)
            if key in computed:
                continue
            if indicator.indicator == "sma" and indicator.window is not None:
                computed[key] = self._compute_sma_series(closes, indicator.window)
            elif indicator.indicator == "ema" and indicator.window is not None:
                computed[key] = self._compute_ema_series(closes, indicator.window)
            elif indicator.indicator == "rsi" and indicator.window is not None:
                computed[key] = self._compute_rsi_series(closes, indicator.window)
            elif indicator.indicator == "macd":
                computed[key] = self._compute_macd_series(closes, indicator)
            elif indicator.indicator == "bollinger_bands" and indicator.window is not None:
                computed[key] = self._compute_bollinger_series(closes, indicator)
            elif indicator.indicator == "atr" and indicator.window is not None:
                computed[key] = self._compute_atr_series(rows, indicator.window)
            elif indicator.indicator == "vwma" and indicator.window is not None:
                computed[key] = self._compute_vwma_series(rows, indicator.window)
        return computed

    def _indicator_values_for_row(
        self,
        indicator: MarketIndicatorSelection,
        *,
        row_index: int,
        row_count: int,
        computed: dict[tuple[object, ...], list[Decimal | None] | dict[str, list[Decimal | None]]],
    ) -> list[RuntimeIndicatorValue]:
        key = self._indicator_selection_key(indicator)
        series = computed[key]
        if indicator.indicator in {"sma", "ema", "rsi", "atr", "vwma"}:
            window = self._required_indicator_window(indicator)
            value = cast(list[Decimal | None], series)[row_index]
            null_reason = self._indicator_null_reason(
                row_index=row_index,
                row_count=row_count,
                required_index=self._required_indicator_index(indicator),
                required_count=self._required_indicator_count(indicator),
                value=value,
                provider_gap=indicator.indicator == "vwma",
            )
            return [
                RuntimeIndicatorValue(
                    name=f"{indicator.indicator}_{window}",
                    value=value,
                    null_reason=null_reason,
                )
            ]
        if indicator.indicator == "macd":
            macd_series = cast(dict[str, list[Decimal | None]], series)
            suffix = self._macd_suffix(indicator)
            return [
                RuntimeIndicatorValue(
                    name=f"macd_{suffix}",
                    value=macd_series["line"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_indicator_index(indicator),
                        required_count=self._required_indicator_count(indicator),
                        value=macd_series["line"][row_index],
                    ),
                ),
                RuntimeIndicatorValue(
                    name=f"macd_signal_{suffix}",
                    value=macd_series["signal"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_macd_signal_index(indicator),
                        required_count=self._required_macd_signal_count(indicator),
                        value=macd_series["signal"][row_index],
                    ),
                ),
                RuntimeIndicatorValue(
                    name=f"macd_histogram_{suffix}",
                    value=macd_series["histogram"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_macd_signal_index(indicator),
                        required_count=self._required_macd_signal_count(indicator),
                        value=macd_series["histogram"][row_index],
                    ),
                ),
            ]
        if indicator.indicator == "bollinger_bands":
            band_series = cast(dict[str, list[Decimal | None]], series)
            suffix = self._bollinger_suffix(indicator)
            return [
                RuntimeIndicatorValue(
                    name=f"bollinger_upper_{suffix}",
                    value=band_series["upper"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_indicator_index(indicator),
                        required_count=self._required_indicator_count(indicator),
                        value=band_series["upper"][row_index],
                    ),
                ),
                RuntimeIndicatorValue(
                    name=f"bollinger_middle_{suffix}",
                    value=band_series["middle"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_indicator_index(indicator),
                        required_count=self._required_indicator_count(indicator),
                        value=band_series["middle"][row_index],
                    ),
                ),
                RuntimeIndicatorValue(
                    name=f"bollinger_lower_{suffix}",
                    value=band_series["lower"][row_index],
                    null_reason=self._indicator_null_reason(
                        row_index=row_index,
                        row_count=row_count,
                        required_index=self._required_indicator_index(indicator),
                        required_count=self._required_indicator_count(indicator),
                        value=band_series["lower"][row_index],
                    ),
                ),
            ]
        raise QuoteProviderError(f"Unsupported indicator {indicator.indicator}")

    def _compute_sma_series(self, values: list[Decimal], window: int) -> list[Decimal | None]:
        series: list[Decimal | None] = []
        for index in range(len(values)):
            if index + 1 < window:
                series.append(None)
                continue
            window_values = values[index + 1 - window : index + 1]
            series.append(sum(window_values, Decimal("0")) / Decimal(window))
        return series

    def _compute_ema_series(self, values: list[Decimal], window: int) -> list[Decimal | None]:
        series: list[Decimal | None] = [None] * len(values)
        if len(values) < window:
            return series
        multiplier = Decimal("2") / Decimal(window + 1)
        previous = sum(values[:window], Decimal("0")) / Decimal(window)
        series[window - 1] = previous
        for index in range(window, len(values)):
            previous = (values[index] - previous) * multiplier + previous
            series[index] = previous
        return series

    def _compute_rsi_series(self, closes: list[Decimal], window: int) -> list[Decimal | None]:
        series: list[Decimal | None] = [None] * len(closes)
        if len(closes) <= window:
            return series
        gains: list[Decimal] = []
        losses: list[Decimal] = []
        for index in range(1, len(closes)):
            change = closes[index] - closes[index - 1]
            gains.append(max(change, Decimal("0")))
            losses.append(max(-change, Decimal("0")))
        average_gain = sum(gains[:window], Decimal("0")) / Decimal(window)
        average_loss = sum(losses[:window], Decimal("0")) / Decimal(window)
        series[window] = self._rsi_value(average_gain, average_loss)
        for index in range(window + 1, len(closes)):
            average_gain = ((average_gain * Decimal(window - 1)) + gains[index - 1]) / Decimal(
                window
            )
            average_loss = ((average_loss * Decimal(window - 1)) + losses[index - 1]) / Decimal(
                window
            )
            series[index] = self._rsi_value(average_gain, average_loss)
        return series

    def _compute_macd_series(
        self,
        closes: list[Decimal],
        indicator: MarketIndicatorSelection,
    ) -> dict[str, list[Decimal | None]]:
        fast_window = self._required_indicator_int(indicator.fast_window, "MACD fast window")
        slow_window = self._required_indicator_int(indicator.slow_window, "MACD slow window")
        signal_window = self._required_indicator_int(
            indicator.signal_window,
            "MACD signal window",
        )
        fast_ema = self._compute_ema_series(closes, fast_window)
        slow_ema = self._compute_ema_series(closes, slow_window)
        line: list[Decimal | None] = []
        for fast_value, slow_value in zip(fast_ema, slow_ema, strict=True):
            line.append(
                fast_value - slow_value
                if fast_value is not None and slow_value is not None
                else None
            )
        signal: list[Decimal | None] = [None] * len(closes)
        macd_entries = [(index, value) for index, value in enumerate(line) if value is not None]
        if len(macd_entries) >= signal_window:
            multiplier = Decimal("2") / Decimal(signal_window + 1)
            previous = sum(
                (value for _, value in macd_entries[:signal_window]),
                Decimal("0"),
            ) / Decimal(signal_window)
            signal[macd_entries[signal_window - 1][0]] = previous
            for index, value in macd_entries[signal_window:]:
                previous = (value - previous) * multiplier + previous
                signal[index] = previous
        histogram = [
            (
                line_value - signal_value
                if line_value is not None and signal_value is not None
                else None
            )
            for line_value, signal_value in zip(line, signal, strict=True)
        ]
        return {"line": line, "signal": signal, "histogram": histogram}

    def _compute_bollinger_series(
        self,
        closes: list[Decimal],
        indicator: MarketIndicatorSelection,
    ) -> dict[str, list[Decimal | None]]:
        window = self._required_indicator_window(indicator)
        deviations = indicator.standard_deviations or Decimal("2")
        upper: list[Decimal | None] = []
        middle: list[Decimal | None] = []
        lower: list[Decimal | None] = []
        for index in range(len(closes)):
            if index + 1 < window:
                upper.append(None)
                middle.append(None)
                lower.append(None)
                continue
            window_values = closes[index + 1 - window : index + 1]
            average = sum(window_values, Decimal("0")) / Decimal(window)
            variance = sum(
                ((value - average) * (value - average) for value in window_values),
                Decimal("0"),
            ) / Decimal(window)
            width = variance.sqrt() * deviations
            upper.append(average + width)
            middle.append(average)
            lower.append(average - width)
        return {"upper": upper, "middle": middle, "lower": lower}

    def _compute_atr_series(
        self,
        rows: list[RuntimeOhlcvRow],
        window: int,
    ) -> list[Decimal | None]:
        true_ranges: list[Decimal] = []
        for index, row in enumerate(rows):
            high_low = row.high - row.low
            if index == 0:
                true_ranges.append(high_low)
                continue
            previous_close = rows[index - 1].close
            true_ranges.append(
                max(
                    high_low,
                    abs(row.high - previous_close),
                    abs(row.low - previous_close),
                )
            )
        series: list[Decimal | None] = [None] * len(rows)
        if len(true_ranges) < window:
            return series
        previous = sum(true_ranges[:window], Decimal("0")) / Decimal(window)
        series[window - 1] = previous
        for index in range(window, len(true_ranges)):
            previous = ((previous * Decimal(window - 1)) + true_ranges[index]) / Decimal(window)
            series[index] = previous
        return series

    def _compute_vwma_series(
        self,
        rows: list[RuntimeOhlcvRow],
        window: int,
    ) -> list[Decimal | None]:
        series: list[Decimal | None] = []
        for index in range(len(rows)):
            if index + 1 < window:
                series.append(None)
                continue
            window_rows = rows[index + 1 - window : index + 1]
            volumes = [row.volume for row in window_rows]
            if any(volume is None for volume in volumes):
                series.append(None)
                continue
            total_volume = sum(Decimal(volume or 0) for volume in volumes)
            if total_volume <= 0:
                series.append(None)
                continue
            weighted_close = sum(
                (row.close * Decimal(row.volume or 0) for row in window_rows),
                Decimal("0"),
            )
            series.append(weighted_close / total_volume)
        return series

    @staticmethod
    def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
        if average_loss == 0:
            return Decimal("50") if average_gain == 0 else Decimal("100")
        relative_strength = average_gain / average_loss
        return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))

    def _indicator_null_reason(
        self,
        *,
        row_index: int,
        row_count: int,
        required_index: int,
        required_count: int,
        value: Decimal | None,
        provider_gap: bool = False,
    ) -> Literal["warmup", "insufficient_history", "provider_gap"] | None:
        if value is not None:
            return None
        if row_count < required_count:
            return "insufficient_history"
        if row_index < required_index:
            return "warmup"
        return "provider_gap" if provider_gap else "insufficient_history"

    def _normalize_indicator_selections(
        self,
        indicators: Sequence[MarketIndicatorSelection],
    ) -> tuple[MarketIndicatorSelection, ...]:
        normalized: list[MarketIndicatorSelection] = []
        seen: set[tuple[object, ...]] = set()
        for indicator in indicators:
            key = self._indicator_selection_key(indicator)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(indicator)
        if not normalized:
            raise QuoteProviderError("At least one indicator is required")
        return tuple(normalized)

    def _indicator_selection_key(self, indicator: MarketIndicatorSelection) -> tuple[object, ...]:
        if indicator.indicator in {"sma", "ema", "rsi", "atr", "vwma"}:
            return (indicator.indicator, self._required_indicator_window(indicator))
        if indicator.indicator == "macd":
            return (
                indicator.indicator,
                self._required_indicator_int(indicator.fast_window, "MACD fast window"),
                self._required_indicator_int(indicator.slow_window, "MACD slow window"),
                self._required_indicator_int(indicator.signal_window, "MACD signal window"),
            )
        if indicator.indicator == "bollinger_bands":
            return (
                indicator.indicator,
                self._required_indicator_window(indicator),
                indicator.standard_deviations or Decimal("2"),
            )
        raise QuoteProviderError(f"Unsupported indicator {indicator.indicator}")

    def _required_indicator_window(self, indicator: MarketIndicatorSelection) -> int:
        return self._required_indicator_int(indicator.window, f"{indicator.indicator} window")

    @staticmethod
    def _required_indicator_int(value: int | None, label: str) -> int:
        if value is None:
            raise QuoteProviderError(f"{label} is required")
        return value

    def _required_indicator_index(self, indicator: MarketIndicatorSelection) -> int:
        if indicator.indicator == "rsi":
            return self._required_indicator_window(indicator)
        if indicator.indicator == "macd":
            return self._required_indicator_int(indicator.slow_window, "MACD slow window") - 1
        return self._required_indicator_window(indicator) - 1

    def _required_indicator_count(self, indicator: MarketIndicatorSelection) -> int:
        return self._required_indicator_index(indicator) + 1

    def _required_macd_signal_index(self, indicator: MarketIndicatorSelection) -> int:
        slow_window = self._required_indicator_int(indicator.slow_window, "MACD slow window")
        signal_window = self._required_indicator_int(
            indicator.signal_window,
            "MACD signal window",
        )
        return slow_window + signal_window - 2

    def _required_macd_signal_count(self, indicator: MarketIndicatorSelection) -> int:
        return self._required_macd_signal_index(indicator) + 1

    def _macd_suffix(self, indicator: MarketIndicatorSelection) -> str:
        fast_window = self._required_indicator_int(indicator.fast_window, "MACD fast window")
        slow_window = self._required_indicator_int(indicator.slow_window, "MACD slow window")
        signal_window = self._required_indicator_int(
            indicator.signal_window,
            "MACD signal window",
        )
        return f"{fast_window}_{slow_window}_{signal_window}"

    def _bollinger_suffix(self, indicator: MarketIndicatorSelection) -> str:
        window = self._required_indicator_window(indicator)
        deviations = self._decimal_name_token(indicator.standard_deviations or Decimal("2"))
        return f"{window}_{deviations}"

    @staticmethod
    def _decimal_name_token(value: Decimal) -> str:
        normalized = value.normalize()
        text = format(normalized, "f")
        return text.replace("-", "minus_").replace(".", "_")

    def _resolve_with_provider_fallback(
        self,
        providers: Sequence[_ProviderT] | None,
        *,
        default_providers: Sequence[_ProviderT],
        operation: str,
        call: Callable[[_ProviderT], _ProviderResultT],
    ) -> tuple[_ProviderResultT | None, list[RuntimeToolWarning]]:
        ordered_providers = list(providers or default_providers)[
            : self.provider_fallback_max_attempts
        ]
        warnings: list[RuntimeToolWarning] = []
        if not ordered_providers:
            warnings.append(
                self._runtime_warning(
                    code=f"{operation}_provider_unavailable",
                    message=f"No {operation} providers are configured",
                    details={"operation": operation},
                )
            )
            return None, warnings

        for provider in ordered_providers:
            provider_name = self._provider_name(provider)
            try:
                return call(provider), warnings
            except (QuoteProviderError, NewsProviderError) as exc:
                warnings.append(
                    self._runtime_warning(
                        code=self._provider_warning_code(operation, exc),
                        message=self._public_warning_message(
                            str(exc) or f"{operation} provider failed"
                        ),
                        details={
                            **self._public_warning_details(exc.details),
                            "operation": operation,
                            "provider": provider_name,
                        },
                    )
                )

        warnings.append(
            self._runtime_warning(
                code=f"{operation}_unavailable",
                message=f"No {operation} data available from configured providers",
                details={"operation": operation},
            )
        )
        return None, warnings

    def _build_fundamental_metrics(
        self, metrics: list[ProviderFundamentalMetric]
    ) -> list[RuntimeFundamentalMetric]:
        return [
            RuntimeFundamentalMetric(
                name=metric.name.strip().lower(),
                value=metric.value,
                currency=metric.currency,
                period=metric.period,
                as_of=to_utc(metric.as_of) if metric.as_of is not None else None,
            )
            for metric in sorted(metrics, key=self._fundamental_metric_sort_key)
        ]

    @staticmethod
    def _fundamental_metric_sort_key(metric: ProviderFundamentalMetric) -> tuple[object, ...]:
        metric_name = metric.name.strip().lower()
        as_of_timestamp = to_utc(metric.as_of).timestamp() if metric.as_of is not None else 0.0
        return (
            _FUNDAMENTAL_METRIC_ORDER.get(metric_name, len(_FUNDAMENTAL_METRIC_ORDER)),
            metric_name,
            metric.period or "",
            -as_of_timestamp,
        )

    @staticmethod
    def _sort_fundamental_statements(
        statements: list[ProviderFinancialStatement],
    ) -> list[ProviderFinancialStatement]:
        return sorted(
            statements,
            key=lambda statement: (
                _FINANCIAL_STATEMENT_TYPE_ORDER.get(statement.statement_type, 99),
                _FINANCIAL_STATEMENT_PERIOD_ORDER.get(statement.period, 99),
                -to_utc(statement.period_end).timestamp(),
            ),
        )

    @staticmethod
    def _sort_fundamental_statement_lines(
        lines: list[ProviderFinancialStatementLine],
    ) -> list[ProviderFinancialStatementLine]:
        return sorted(
            lines,
            key=lambda line: (
                _FINANCIAL_STATEMENT_LINE_ORDER.get(
                    line.name, len(_FINANCIAL_STATEMENT_LINE_ORDER)
                ),
                line.name,
            ),
        )

    def _build_news_items(
        self,
        items: list[ProviderNewsItem],
        *,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> list[RuntimeNewsItem]:
        sorted_items = sorted(items, key=lambda item: to_utc(item.published_at), reverse=True)
        return [
            RuntimeNewsItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=to_utc(item.published_at),
                summary=item.summary,
                symbols=[normalize_symbol(symbol) for symbol in item.symbols or []],
                sentiment=item.sentiment,
            )
            for item in sorted_items
            if self._news_item_within_bounds(
                item,
                start_date=start_date,
                end_date=end_date,
            )
        ]

    @staticmethod
    def _news_item_within_bounds(
        item: ProviderNewsItem,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> bool:
        published_at = to_utc(item.published_at)
        if start_date is not None and published_at < start_date:
            return False
        if end_date is not None and published_at > end_date:
            return False
        return True

    def _build_insider_transactions(
        self, transactions: list[ProviderInsiderTransaction]
    ) -> list[RuntimeInsiderTransaction]:
        sorted_transactions = sorted(
            transactions,
            key=lambda transaction: to_utc(transaction.transaction_date),
            reverse=True,
        )
        return [
            RuntimeInsiderTransaction(
                insider_name=transaction.insider_name,
                role=transaction.role,
                transaction_type=transaction.transaction_type,
                shares=transaction.shares,
                price=transaction.price,
                value=transaction.value,
                filed_at=(
                    to_utc(transaction.filed_at) if transaction.filed_at is not None else None
                ),
                transaction_date=to_utc(transaction.transaction_date),
            )
            for transaction in sorted_transactions
        ]

    def _normalize_optional_symbols(self, symbols: list[str]) -> list[str]:
        normalized_symbols: list[str] = []
        seen_symbols: set[str] = set()
        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            normalized_symbols.append(symbol)
        return normalized_symbols

    @staticmethod
    def _normalize_news_scope(
        scope: NewsScope | None,
        *,
        symbols: list[str],
    ) -> NewsScope:
        if scope is None:
            return "symbol" if symbols else "market"
        normalized_scope = scope.strip().lower()
        if normalized_scope not in {"symbol", "market", "global"}:
            raise QuoteProviderError("News scope must be symbol, market, or global")
        if normalized_scope == "symbol" and not symbols:
            raise QuoteProviderError("News scope symbol requires symbols")
        return cast(NewsScope, normalized_scope)

    def _normalize_result_limit(
        self,
        limit: int | None,
        *,
        default_limit: int,
        max_limit: int,
        label: str,
    ) -> int:
        if limit is None:
            return default_limit
        if limit < 1:
            raise QuoteProviderError(f"{label} must be at least 1")
        if limit > max_limit:
            raise QuoteProviderError(f"{label} must be at most {max_limit}")
        return limit

    def _provider_warning_code(
        self, operation: str, exc: QuoteProviderError | NewsProviderError
    ) -> str:
        if exc.code == "provider_api_key_missing":
            return f"{operation}_api_key_missing"
        if exc.code == "provider_timeout":
            return f"{operation}_provider_timeout"
        if exc.code == "provider_rate_limited":
            return f"{operation}_provider_rate_limited"
        if exc.code == "provider_unsupported_query":
            return f"{operation}_provider_unsupported_query"
        if exc.code == "provider_unavailable":
            return f"{operation}_provider_unavailable"
        return f"{operation}_provider_error"

    def _provider_name(self, provider: QuoteProvider | NewsProvider) -> str:
        return str(getattr(provider, "provider_name", provider.__class__.__name__))

    def _runtime_warning(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, str],
    ) -> RuntimeToolWarning:
        return RuntimeToolWarning(
            code=code,
            message=self._public_warning_message(message),
            details=self._public_warning_details(details),
        )

    @staticmethod
    def _public_warning_message(message: str) -> str:
        redacted_assignments = _SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
            message,
        )
        return _SECRET_TOKEN_RE.sub("<redacted>", redacted_assignments)

    @classmethod
    def _public_warning_details(cls, details: dict[str, str]) -> dict[str, str]:
        public_details: dict[str, str] = {}
        for key, value in details.items():
            normalized_key = key.strip()
            if not normalized_key or _SENSITIVE_WARNING_DETAIL_KEY_RE.search(normalized_key):
                continue
            key_tokens = _WARNING_DETAIL_KEY_TOKEN_RE.sub("_", normalized_key).strip("_")
            if not key_tokens:
                continue
            public_details[to_camel(key_tokens)] = cls._public_warning_message(value)
        return public_details

    def _normalize_ohlcv_row_limit(self, row_limit: int | None) -> int:
        if row_limit is None:
            return self.ohlcv_default_row_limit
        if row_limit < 1:
            raise QuoteProviderError("OHLCV rowLimit must be at least 1")
        if row_limit > self.ohlcv_max_row_limit:
            raise QuoteProviderError(f"OHLCV rowLimit must be at most {self.ohlcv_max_row_limit}")
        return row_limit

    def _resolve_quote(self, symbol: str) -> tuple[MarketQuoteRead | None, str | None, bool]:
        try:
            provider_quote = self.quote_provider.fetch_quote(symbol)
        except QuoteProviderError:
            return None, f"No fresh quote available for {symbol}", False

        if provider_quote.currency != DEFAULT_CURRENCY:
            return None, f"Quote currency mismatch for {symbol}", False

        is_stale = self._is_quote_stale(provider_quote.as_of)
        cached = self.repository.get_by_provider_symbol_as_of(
            provider_quote.provider,
            provider_quote.symbol,
            provider_quote.as_of,
        )
        if cached is None:
            cached = MarketQuote(
                symbol=provider_quote.symbol,
                provider=provider_quote.provider,
                price=provider_quote.price,
                previous_close=provider_quote.previous_close,
                currency=provider_quote.currency,
                name=provider_quote.name,
                as_of=provider_quote.as_of,
                fetched_at=utcnow(),
                is_stale=is_stale,
            )
            _ = self.repository.add(cached)
        else:
            cached.price = provider_quote.price
            cached.previous_close = provider_quote.previous_close
            cached.currency = provider_quote.currency
            cached.name = provider_quote.name
            cached.fetched_at = utcnow()
            cached.is_stale = is_stale

        return (
            self._to_market_quote_read(cached, previous_close=provider_quote.previous_close),
            None,
            True,
        )

    def _is_quote_stale(self, as_of: datetime | None) -> bool:
        if as_of is None:
            return True
        stale_cutoff = utcnow() - timedelta(minutes=self.quote_stale_after_minutes)
        return to_utc(as_of) < stale_cutoff

    def _to_market_quote_read(
        self, quote: MarketQuote, *, previous_close: Decimal | None
    ) -> MarketQuoteRead:
        return MarketQuoteRead(
            symbol=quote.symbol,
            name=quote.name,
            price=quote.price,
            previous_close=previous_close,
            currency=quote.currency,
            provider=quote.provider,
            as_of=quote.as_of,
            is_stale=quote.is_stale,
        )
