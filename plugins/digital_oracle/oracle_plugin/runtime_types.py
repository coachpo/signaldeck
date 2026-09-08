from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from oracle_plugin.contracts import RuntimeToolWarning
from plugin_runtime.common import CamelModel, ensure_timezone
from pydantic import Field, field_validator

PREDICTION_MARKETS_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/prediction_markets_lookup"
SEC_FILINGS_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/sec_filings_lookup"
MARKET_SENTIMENT_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/market_sentiment_lookup"
MACRO_RATES_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/macro_rates_lookup"
CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/crypto_derivatives_lookup"
CFTC_POSITIONING_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/cftc_positioning_lookup"
OPTIONS_LOOKUP_TOOL_KEY = "signaldeck/digital-oracle/options_lookup"

NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS = (
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    OPTIONS_LOOKUP_TOOL_KEY,
)


def _validate_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_timezone(value)


class RuntimePredictionMarketOrderBookLevel(CamelModel):
    price: Decimal
    size: Decimal | None = None


class RuntimePredictionMarketOrderBook(CamelModel):
    bids: list[RuntimePredictionMarketOrderBookLevel] = Field(default_factory=list)
    asks: list[RuntimePredictionMarketOrderBookLevel] = Field(default_factory=list)
    spread: Decimal | None = None
    depth_limit: int | None = Field(default=None, ge=1)


class RuntimePredictionMarketContract(CamelModel):
    contract_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    probability: Decimal | None = None
    yes_price: Decimal | None = None
    no_price: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    order_book: RuntimePredictionMarketOrderBook | None = None


class RuntimePredictionMarketEvent(CamelModel):
    venue: Literal["polymarket", "kalshi"]
    event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)
    url: str | None = None
    end_date: datetime | None = None
    contracts: list[RuntimePredictionMarketContract]

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimePredictionMarketsLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/prediction_markets_lookup"] = (
        "signaldeck/digital-oracle/prediction_markets_lookup"
    )
    query: str = Field(min_length=1)
    events: list[RuntimePredictionMarketEvent]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeSecFiling(CamelModel):
    accession_number: str = Field(min_length=1)
    form_type: str = Field(min_length=1)
    filing_date: date
    accepted_at: datetime | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None

    @field_validator("accepted_at")
    @classmethod
    def validate_accepted_at(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeSecSearchHit(CamelModel):
    accession_number: str = Field(min_length=1)
    form_type: str = Field(min_length=1)
    filing_date: date
    cik: str | None = None
    ticker: str | None = None
    entity_name: str | None = None
    primary_document: str | None = None
    url: str | None = None
    description: str | None = None
    matched_text: str | None = None


class RuntimeSecOwnershipTransaction(CamelModel):
    accession_number: str = Field(min_length=1)
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


class RuntimeSecFilingsLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/sec_filings_lookup"] = (
        "signaldeck/digital-oracle/sec_filings_lookup"
    )
    ticker: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    cik: str | None = None
    entity_name: str | None = None
    filings: list[RuntimeSecFiling]
    search_hits: list[RuntimeSecSearchHit] = Field(default_factory=list)
    ownership_transactions: list[RuntimeSecOwnershipTransaction] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeMarketSentimentLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/market_sentiment_lookup"] = (
        "signaldeck/digital-oracle/market_sentiment_lookup"
    )
    indicator: Literal["fear_greed"]
    as_of_date: date | None = None
    provider: str = Field(min_length=1)
    score: int | None = Field(default=None, ge=0, le=100)
    label: str | None = None
    previous_close: int | None = Field(default=None, ge=0, le=100)
    week_ago: int | None = Field(default=None, ge=0, le=100)
    month_ago: int | None = Field(default=None, ge=0, le=100)
    year_ago: int | None = Field(default=None, ge=0, le=100)
    source_url: str | None = None
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeMacroRatesSeries(CamelModel):
    provider: str = Field(min_length=1)
    family: Literal[
        "macro_indicators",
        "yield_curve",
        "fx_rates",
        "policy_rates",
        "credit_gaps",
        "fedwatch",
    ]
    series_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    country: str | None = Field(default=None, min_length=1)
    currency: str | None = Field(default=None, min_length=1)
    unit: str | None = None
    date: date
    value: Decimal
    tenor: str | None = Field(default=None, min_length=1)
    source_url: str | None = None


class RuntimeMacroRatesLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/macro_rates_lookup"] = (
        "signaldeck/digital-oracle/macro_rates_lookup"
    )
    query: str | None = Field(default=None, min_length=1)
    series: list[RuntimeMacroRatesSeries]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeCryptoDerivativesOrderBookLevel(CamelModel):
    price: Decimal
    size: Decimal


class RuntimeCryptoDerivativesOrderBook(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    bids: list[RuntimeCryptoDerivativesOrderBookLevel] = Field(default_factory=list)
    asks: list[RuntimeCryptoDerivativesOrderBookLevel] = Field(default_factory=list)
    depth_limit: int | None = Field(default=None, ge=1)


class RuntimeCryptoDerivativesSpotQuote(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    price: Decimal
    currency: str = Field(min_length=1)
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeCryptoDerivativesGlobalMetrics(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str | None = Field(default=None, min_length=1)
    market_cap: Decimal | None = None
    volume_24h: Decimal | None = None
    open_interest: Decimal | None = None
    as_of: datetime | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime | None) -> datetime | None:
        return _validate_datetime(value)


class RuntimeCryptoDerivativesTermPoint(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    expiry_date: date
    instrument: str = Field(min_length=1)
    implied_volatility: Decimal | None = None
    open_interest: Decimal | None = None


class RuntimeCryptoDerivativesOptionSummary(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    expiry_date: date
    strike: Decimal
    option_type: Literal["call", "put"]
    implied_volatility: Decimal | None = None
    open_interest: Decimal | None = None


class RuntimeCryptoDerivativesLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/crypto_derivatives_lookup"] = (
        "signaldeck/digital-oracle/crypto_derivatives_lookup"
    )
    assets: list[str]
    spot: list[RuntimeCryptoDerivativesSpotQuote] = Field(default_factory=list)
    global_metrics: list[RuntimeCryptoDerivativesGlobalMetrics] = Field(default_factory=list)
    term_structure: list[RuntimeCryptoDerivativesTermPoint] = Field(default_factory=list)
    options: list[RuntimeCryptoDerivativesOptionSummary] = Field(default_factory=list)
    order_books: list[RuntimeCryptoDerivativesOrderBook] = Field(default_factory=list)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeCftcPositioningRow(CamelModel):
    market: str = Field(min_length=1)
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


class RuntimeCftcPositioningReport(CamelModel):
    provider: str = Field(min_length=1)
    report_type: str = Field(min_length=1)
    report_date: date
    rows: list[RuntimeCftcPositioningRow]


class RuntimeCftcPositioningLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/cftc_positioning_lookup"] = (
        "signaldeck/digital-oracle/cftc_positioning_lookup"
    )
    reports: list[RuntimeCftcPositioningReport]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeOptionGreeks(CamelModel):
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    implied_volatility: Decimal | None = None


class RuntimeOptionContract(CamelModel):
    contract_symbol: str = Field(min_length=1)
    strike: Decimal
    last_price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    greeks: RuntimeOptionGreeks | None = None


class RuntimeOptionsChain(CamelModel):
    provider: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    expiry_date: date
    calls: list[RuntimeOptionContract] = Field(default_factory=list)
    puts: list[RuntimeOptionContract] = Field(default_factory=list)


class RuntimeOptionsLookupResult(CamelModel):
    tool_key: Literal["signaldeck/digital-oracle/options_lookup"] = (
        "signaldeck/digital-oracle/options_lookup"
    )
    symbol: str = Field(min_length=1)
    chains: list[RuntimeOptionsChain]
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


class RuntimeDigitalOracleUnavailableLookupResult(CamelModel):
    tool_key: str = Field(min_length=1)
    warnings: list[RuntimeToolWarning] = Field(default_factory=list)


__all__ = [
    "CFTC_POSITIONING_LOOKUP_TOOL_KEY",
    "CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY",
    "MACRO_RATES_LOOKUP_TOOL_KEY",
    "MARKET_SENTIMENT_LOOKUP_TOOL_KEY",
    "NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS",
    "OPTIONS_LOOKUP_TOOL_KEY",
    "PREDICTION_MARKETS_LOOKUP_TOOL_KEY",
    "SEC_FILINGS_LOOKUP_TOOL_KEY",
    "RuntimeCftcPositioningLookupResult",
    "RuntimeCftcPositioningReport",
    "RuntimeCftcPositioningRow",
    "RuntimeCryptoDerivativesGlobalMetrics",
    "RuntimeCryptoDerivativesLookupResult",
    "RuntimeCryptoDerivativesOptionSummary",
    "RuntimeCryptoDerivativesOrderBook",
    "RuntimeCryptoDerivativesOrderBookLevel",
    "RuntimeCryptoDerivativesSpotQuote",
    "RuntimeCryptoDerivativesTermPoint",
    "RuntimeDigitalOracleUnavailableLookupResult",
    "RuntimeMacroRatesLookupResult",
    "RuntimeMacroRatesSeries",
    "RuntimeMarketSentimentLookupResult",
    "RuntimeOptionContract",
    "RuntimeOptionGreeks",
    "RuntimeOptionsChain",
    "RuntimeOptionsLookupResult",
    "RuntimePredictionMarketContract",
    "RuntimePredictionMarketEvent",
    "RuntimePredictionMarketOrderBook",
    "RuntimePredictionMarketOrderBookLevel",
    "RuntimePredictionMarketsLookupResult",
    "RuntimeSecFiling",
    "RuntimeSecFilingsLookupResult",
    "RuntimeSecOwnershipTransaction",
    "RuntimeSecSearchHit",
]
