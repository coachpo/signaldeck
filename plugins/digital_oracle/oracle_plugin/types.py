from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol

from oracle_plugin.contracts import RuntimeToolWarning

from .config import (
    CftcPositioningReportType,
    CryptoDerivativesDataType,
    CryptoDerivativesVenue,
    MacroRatesFamily,
    MacroRatesSource,
    MarketSentimentIndicator,
    OptionsMoneyness,
    PredictionMarketVenue,
)


def _empty_warnings() -> tuple[RuntimeToolWarning, ...]:
    return ()


class DigitalOracleProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.details: Mapping[str, object] = details or {}


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsQuery:
    query: str
    venues: tuple[PredictionMarketVenue, ...] | None = None
    item_limit: int | None = None
    include_resolved: bool = False
    include_order_book: bool = False
    depth_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsProviderQuery:
    query: str
    venue: PredictionMarketVenue
    item_limit: int
    include_resolved: bool
    timeout_seconds: float
    include_order_book: bool = False
    depth_limit: int = 5


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketOrderBookLevel:
    price: Decimal
    size: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketOrderBook:
    bids: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = field(default_factory=tuple)
    asks: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = field(default_factory=tuple)
    spread: Decimal | None = None
    depth_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketContract:
    contract_id: str
    title: str
    probability: Decimal | None = None
    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    order_book: DigitalOraclePredictionMarketOrderBook | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketEvent:
    venue: PredictionMarketVenue
    event_id: str
    title: str
    status: str
    url: str | None = None
    end_date: datetime | None = None
    contracts: tuple[DigitalOraclePredictionMarketContract, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsProviderResult:
    provider: PredictionMarketVenue
    events: tuple[DigitalOraclePredictionMarketEvent, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOraclePredictionMarketsResult:
    query: str
    events: tuple[DigitalOraclePredictionMarketEvent, ...]
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsQuery:
    ticker: str | None = None
    query: str | None = None
    cik: str | None = None
    form_types: tuple[str, ...] | None = None
    start_date: date | None = None
    end_date: date | None = None
    item_limit: int | None = None
    include_ownership_transactions: bool = False


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsProviderQuery:
    ticker: str | None
    form_types: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    item_limit: int
    edgar_contact_email: str
    timeout_seconds: float
    query: str | None = None
    cik: str | None = None
    include_ownership_transactions: bool = False


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFiling:
    accession_number: str
    form_type: str
    filing_date: date
    accepted_at: datetime | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecSearchHit:
    accession_number: str
    form_type: str
    filing_date: date
    cik: str | None = None
    ticker: str | None = None
    entity_name: str | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None
    matched_text: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecOwnershipTransaction:
    accession_number: str
    filing_date: date
    issuer_name: str | None = None
    issuer_ticker: str | None = None
    reporting_owner_name: str | None = None
    transaction_date: date | None = None
    transaction_code: str | None = None
    acquired_disposed_code: str | None = None
    shares: Decimal | None = None
    price: Decimal | None = None
    ownership_nature: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsProviderResult:
    provider: str
    ticker: str | None
    cik: str | None = None
    entity_name: str | None = None
    filings: tuple[DigitalOracleSecFiling, ...] = field(default_factory=tuple)
    search_hits: tuple[DigitalOracleSecSearchHit, ...] = field(default_factory=tuple)
    ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleSecFilingsResult:
    ticker: str | None = None
    query: str | None = None
    cik: str | None = None
    entity_name: str | None = None
    filings: tuple[DigitalOracleSecFiling, ...] = field(default_factory=tuple)
    search_hits: tuple[DigitalOracleSecSearchHit, ...] = field(default_factory=tuple)
    ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = field(
        default_factory=tuple
    )
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentQuery:
    indicator: MarketSentimentIndicator = "fear_greed"
    as_of_date: date | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentProviderQuery:
    indicator: MarketSentimentIndicator
    as_of_date: date | None
    source_url: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentProviderResult:
    provider: str
    score: int | None = None
    label: str | None = None
    as_of_date: date | None = None
    previous_close: int | None = None
    week_ago: int | None = None
    month_ago: int | None = None
    year_ago: int | None = None
    source_url: str | None = None
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMarketSentimentResult:
    indicator: MarketSentimentIndicator
    provider: str
    as_of_date: date | None = None
    score: int | None = None
    label: str | None = None
    previous_close: int | None = None
    week_ago: int | None = None
    month_ago: int | None = None
    year_ago: int | None = None
    source_url: str | None = None
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMacroRatesSeries:
    provider: str
    family: MacroRatesFamily
    series_id: str
    label: str
    country: str | None
    currency: str | None
    unit: str
    date: date
    value: Decimal
    tenor: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleMacroRatesQuery:
    query: str | None = None
    sources: tuple[MacroRatesSource, ...] | None = None
    families: tuple[MacroRatesFamily, ...] | None = None
    series_ids: tuple[str, ...] | None = None
    countries: tuple[str, ...] | None = None
    start_date: date | None = None
    end_date: date | None = None
    as_of_date: date | None = None
    item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleMacroRatesProviderQuery:
    source: MacroRatesSource
    query: str | None
    families: tuple[MacroRatesFamily, ...] | None
    series_ids: tuple[str, ...] | None
    countries: tuple[str, ...] | None
    start_date: date | None
    end_date: date | None
    as_of_date: date | None
    item_limit: int
    timeout_seconds: float
    fred_api_key: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleMacroRatesProviderResult:
    provider: MacroRatesSource
    series: tuple[DigitalOracleMacroRatesSeries, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleMacroRatesResult:
    query: str | None = None
    series: tuple[DigitalOracleMacroRatesSeries, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesOrderBookLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesOrderBook:
    provider: str
    symbol: str
    instrument: str
    bids: tuple[DigitalOracleCryptoDerivativesOrderBookLevel, ...] = field(default_factory=tuple)
    asks: tuple[DigitalOracleCryptoDerivativesOrderBookLevel, ...] = field(default_factory=tuple)
    depth_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesSpotQuote:
    provider: str
    symbol: str
    price: Decimal
    currency: str
    as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesGlobalMetrics:
    provider: str
    symbol: str | None = None
    market_cap: Decimal | None = None
    volume_24h: Decimal | None = None
    open_interest: Decimal | None = None
    as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesTermPoint:
    provider: str
    symbol: str
    expiry_date: date
    instrument: str
    implied_volatility: Decimal | None = None
    open_interest: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesOptionSummary:
    provider: str
    symbol: str
    expiry_date: date
    strike: Decimal
    option_type: Literal["call", "put"]
    implied_volatility: Decimal | None = None
    open_interest: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesProviderResult:
    provider: str
    spot: tuple[DigitalOracleCryptoDerivativesSpotQuote, ...] = field(default_factory=tuple)
    global_metrics: tuple[DigitalOracleCryptoDerivativesGlobalMetrics, ...] = field(
        default_factory=tuple
    )
    term_structure: tuple[DigitalOracleCryptoDerivativesTermPoint, ...] = field(
        default_factory=tuple
    )
    options: tuple[DigitalOracleCryptoDerivativesOptionSummary, ...] = field(default_factory=tuple)
    order_books: tuple[DigitalOracleCryptoDerivativesOrderBook, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesQuery:
    assets: tuple[str, ...] | None = None
    venues: tuple[CryptoDerivativesVenue, ...] | None = None
    data_types: tuple[CryptoDerivativesDataType, ...] | None = None
    expirations: tuple[date, ...] | None = None
    include_order_book: bool = False
    depth_limit: int | None = None
    item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesProviderQuery:
    venue: CryptoDerivativesVenue
    assets: tuple[str, ...]
    data_types: tuple[CryptoDerivativesDataType, ...]
    expirations: tuple[date, ...] | None
    include_order_book: bool
    depth_limit: int
    item_limit: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class DigitalOracleCryptoDerivativesResult:
    assets: tuple[str, ...]
    spot: tuple[DigitalOracleCryptoDerivativesSpotQuote, ...] = field(default_factory=tuple)
    global_metrics: tuple[DigitalOracleCryptoDerivativesGlobalMetrics, ...] = field(
        default_factory=tuple
    )
    term_structure: tuple[DigitalOracleCryptoDerivativesTermPoint, ...] = field(
        default_factory=tuple
    )
    options: tuple[DigitalOracleCryptoDerivativesOptionSummary, ...] = field(default_factory=tuple)
    order_books: tuple[DigitalOracleCryptoDerivativesOrderBook, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningRow:
    market: str
    contract_market_code: str | None = None
    non_commercial_long: Decimal | None = None
    non_commercial_short: Decimal | None = None
    non_commercial_spreading: Decimal | None = None
    non_commercial_net: Decimal | None = None
    commercial_long: Decimal | None = None
    commercial_short: Decimal | None = None
    commercial_net: Decimal | None = None
    producer_long: Decimal | None = None
    producer_short: Decimal | None = None
    producer_net: Decimal | None = None
    swap_dealer_long: Decimal | None = None
    swap_dealer_short: Decimal | None = None
    swap_dealer_net: Decimal | None = None
    managed_money_long: Decimal | None = None
    managed_money_short: Decimal | None = None
    managed_money_spreading: Decimal | None = None
    managed_money_net: Decimal | None = None
    other_reportable_long: Decimal | None = None
    other_reportable_short: Decimal | None = None
    other_reportable_spreading: Decimal | None = None
    other_reportable_net: Decimal | None = None
    open_interest: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningReport:
    provider: str
    report_type: CftcPositioningReportType
    report_date: date
    rows: tuple[DigitalOracleCftcPositioningRow, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningProviderResult:
    provider: str
    reports: tuple[DigitalOracleCftcPositioningReport, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningQuery:
    markets: tuple[str, ...] | None = None
    report_types: tuple[CftcPositioningReportType, ...] | None = None
    start_date: date | None = None
    end_date: date | None = None
    item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningProviderQuery:
    markets: tuple[str, ...]
    report_types: tuple[CftcPositioningReportType, ...]
    start_date: date | None
    end_date: date | None
    item_limit: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class DigitalOracleCftcPositioningResult:
    reports: tuple[DigitalOracleCftcPositioningReport, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionGreeks:
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    implied_volatility: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionContract:
    contract_symbol: str
    strike: Decimal
    last_price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    greeks: DigitalOracleOptionGreeks | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionsChain:
    provider: str
    symbol: str
    expiry_date: date
    calls: tuple[DigitalOracleOptionContract, ...] = field(default_factory=tuple)
    puts: tuple[DigitalOracleOptionContract, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionsProviderResult:
    provider: str
    chains: tuple[DigitalOracleOptionsChain, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionsQuery:
    symbols: tuple[str, ...]
    expirations: tuple[date, ...] | None = None
    include_greeks: bool = False
    moneyness: OptionsMoneyness = "all"
    item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionsProviderQuery:
    symbol: str
    expirations: tuple[date, ...] | None
    include_greeks: bool
    moneyness: OptionsMoneyness
    item_limit: int
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class DigitalOracleOptionsResult:
    symbol: str
    chains: tuple[DigitalOracleOptionsChain, ...] = field(default_factory=tuple)
    warnings: tuple[RuntimeToolWarning, ...] = field(default_factory=_empty_warnings)


class DigitalOraclePredictionMarketProvider(Protocol):
    venue: PredictionMarketVenue

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult: ...


class DigitalOracleSecFilingsProvider(Protocol):
    provider_name: str

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult: ...


class DigitalOracleMarketSentimentProvider(Protocol):
    provider_name: str

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentProviderQuery,
    ) -> DigitalOracleMarketSentimentProviderResult: ...


class DigitalOracleMacroRatesProvider(Protocol):
    source: MacroRatesSource

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult: ...


class DigitalOracleCryptoDerivativesProvider(Protocol):
    venue: CryptoDerivativesVenue

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesProviderQuery,
    ) -> DigitalOracleCryptoDerivativesProviderResult: ...


class DigitalOracleCftcPositioningProvider(Protocol):
    provider_name: str

    def lookup_cftc_positioning(
        self,
        query: DigitalOracleCftcPositioningProviderQuery,
    ) -> DigitalOracleCftcPositioningProviderResult: ...


class DigitalOracleOptionsProvider(Protocol):
    provider_name: str

    def lookup_options(
        self,
        query: DigitalOracleOptionsProviderQuery,
    ) -> DigitalOracleOptionsProviderResult: ...


__all__ = [
    "DigitalOracleCftcPositioningProviderResult",
    "DigitalOracleCftcPositioningProvider",
    "DigitalOracleCftcPositioningProviderQuery",
    "DigitalOracleCftcPositioningQuery",
    "DigitalOracleCftcPositioningReport",
    "DigitalOracleCftcPositioningResult",
    "DigitalOracleCftcPositioningRow",
    "DigitalOracleCryptoDerivativesGlobalMetrics",
    "DigitalOracleCryptoDerivativesOptionSummary",
    "DigitalOracleCryptoDerivativesOrderBook",
    "DigitalOracleCryptoDerivativesOrderBookLevel",
    "DigitalOracleCryptoDerivativesProvider",
    "DigitalOracleCryptoDerivativesProviderQuery",
    "DigitalOracleCryptoDerivativesProviderResult",
    "DigitalOracleCryptoDerivativesQuery",
    "DigitalOracleCryptoDerivativesResult",
    "DigitalOracleCryptoDerivativesSpotQuote",
    "DigitalOracleCryptoDerivativesTermPoint",
    "DigitalOracleMacroRatesProvider",
    "DigitalOracleMacroRatesProviderQuery",
    "DigitalOracleMacroRatesProviderResult",
    "DigitalOracleMacroRatesQuery",
    "DigitalOracleMacroRatesResult",
    "DigitalOracleMacroRatesSeries",
    "DigitalOracleMarketSentimentProvider",
    "DigitalOracleMarketSentimentProviderQuery",
    "DigitalOracleMarketSentimentProviderResult",
    "DigitalOracleMarketSentimentQuery",
    "DigitalOracleMarketSentimentResult",
    "DigitalOracleOptionContract",
    "DigitalOracleOptionGreeks",
    "DigitalOracleOptionsChain",
    "DigitalOracleOptionsProvider",
    "DigitalOracleOptionsProviderQuery",
    "DigitalOracleOptionsProviderResult",
    "DigitalOracleOptionsQuery",
    "DigitalOracleOptionsResult",
    "DigitalOraclePredictionMarketContract",
    "DigitalOraclePredictionMarketEvent",
    "DigitalOraclePredictionMarketOrderBook",
    "DigitalOraclePredictionMarketOrderBookLevel",
    "DigitalOraclePredictionMarketProvider",
    "DigitalOraclePredictionMarketsProviderQuery",
    "DigitalOraclePredictionMarketsProviderResult",
    "DigitalOraclePredictionMarketsQuery",
    "DigitalOraclePredictionMarketsResult",
    "DigitalOracleProviderError",
    "DigitalOracleSecFiling",
    "DigitalOracleSecFilingsProvider",
    "DigitalOracleSecFilingsProviderQuery",
    "DigitalOracleSecFilingsProviderResult",
    "DigitalOracleSecFilingsQuery",
    "DigitalOracleSecFilingsResult",
    "DigitalOracleSecOwnershipTransaction",
    "DigitalOracleSecSearchHit",
]
