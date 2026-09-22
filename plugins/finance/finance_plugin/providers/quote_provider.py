from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from plugin_runtime.formatting import normalize_symbol, to_utc

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

    def fetch_holders(self, symbol: str) -> HoldersSnapshot: ...

    def fetch_analyst_estimates(self, symbol: str) -> AnalystEstimatesSnapshot: ...


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

    def fetch_holders(self, symbol: str) -> HoldersSnapshot:
        reported = date(2024, 3, 31)
        return HoldersSnapshot(
            symbol=normalize_symbol(symbol),
            provider=self.provider_name,
            breakdown=OwnershipBreakdown(
                insiders_percent=Decimal("1.5"),
                institutions_percent=Decimal("60.2"),
                institutions_float_percent=Decimal("61.1"),
                institution_count=4200,
            ),
            institutions=[
                HolderPosition(
                    holder="Deterministic Institution",
                    report_date=reported,
                    percent_held=Decimal("7.5"),
                    shares=1000000,
                    value=Decimal("180000000"),
                    percent_change=Decimal("1.2"),
                )
            ],
            funds=[
                HolderPosition(
                    holder="Deterministic Fund",
                    report_date=reported,
                    percent_held=Decimal("3.1"),
                    shares=400000,
                    value=Decimal("72000000"),
                    percent_change=Decimal("-0.4"),
                )
            ],
            insiders=[
                InsiderHolding(
                    name="Deterministic Insider",
                    position="Director",
                    latest_transaction="Purchase",
                    latest_transaction_date=date(2024, 3, 29),
                    shares_owned_directly=10000,
                    position_direct_date=date(2024, 3, 29),
                )
            ],
        )

    def fetch_analyst_estimates(self, symbol: str) -> AnalystEstimatesSnapshot:
        return AnalystEstimatesSnapshot(
            symbol=normalize_symbol(symbol),
            provider=self.provider_name,
            periods=[
                EstimatePeriod(
                    period="0q",
                    eps=EstimateRange(
                        average=Decimal("1.5"),
                        low=Decimal("1.4"),
                        high=Decimal("1.6"),
                        year_ago=Decimal("1.3"),
                        analyst_count=20,
                        growth_percent=Decimal("15.4"),
                        currency="USD",
                    ),
                    revenue=EstimateRange(
                        average=Decimal("90000000000"),
                        low=Decimal("88000000000"),
                        high=Decimal("92000000000"),
                        year_ago=Decimal("85000000000"),
                        analyst_count=18,
                        growth_percent=Decimal("5.9"),
                        currency="USD",
                    ),
                    eps_trend=EpsTrend(
                        current=Decimal("1.5"),
                        seven_days_ago=Decimal("1.5"),
                        thirty_days_ago=Decimal("1.48"),
                        sixty_days_ago=Decimal("1.45"),
                        ninety_days_ago=Decimal("1.44"),
                    ),
                    eps_revisions=EpsRevisions(
                        up_last7_days=1, up_last30_days=3, down_last7_days=0, down_last30_days=1
                    ),
                )
            ],
            price_target=PriceTarget(
                current=Decimal("180.5"),
                high=Decimal("220"),
                low=Decimal("150"),
                mean=Decimal("195.2"),
                median=Decimal("197"),
            ),
            recommendations=[
                RecommendationCount(
                    period="0m", strong_buy=5, buy=10, hold=8, sell=1, strong_sell=0
                )
            ],
            earnings_history=[
                EarningsSurprise(
                    quarter_end=date(2023, 12, 31),
                    eps_actual=Decimal("1.4"),
                    eps_estimate=Decimal("1.35"),
                    eps_difference=Decimal("0.05"),
                    surprise_percent=Decimal("3.7"),
                )
            ],
            rating_changes=[
                RatingChange(
                    at=datetime(2024, 3, 28, 12, tzinfo=UTC),
                    firm="Deterministic Securities",
                    to_grade="Buy",
                    from_grade="Hold",
                    action="up",
                    price_target_action="Raises",
                    current_price_target=Decimal("200"),
                    prior_price_target=Decimal("185"),
                )
            ],
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
