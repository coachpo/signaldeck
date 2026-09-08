from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from oracle_plugin.settings import (
    DigitalOracleSettings,
    get_digital_oracle_settings,
    reset_digital_oracle_settings_cache,
)

PredictionMarketVenue = Literal["polymarket", "kalshi"]
MarketSentimentIndicator = Literal["fear_greed"]
MacroRatesSource = Literal["treasury", "bis", "worldbank", "cme_fedwatch", "fred"]
CryptoDerivativesVenue = Literal["coingecko", "deribit"]
CryptoDerivativesDataType = Literal[
    "spot",
    "global_market",
    "term_structure",
    "option_chain",
    "order_book",
]
CftcPositioningReportType = Literal[
    "legacy_futures_only",
    "legacy_combined",
    "disaggregated_futures_only",
    "disaggregated_combined",
    "financial_futures",
]
OptionsMoneyness = Literal["all", "itm", "otm", "near_the_money"]
MacroRatesFamily = Literal[
    "macro_indicators",
    "yield_curve",
    "fx_rates",
    "policy_rates",
    "credit_gaps",
    "fedwatch",
]

PREDICTION_MARKET_VENUES: tuple[PredictionMarketVenue, ...] = ("polymarket", "kalshi")
MACRO_RATES_SOURCES: tuple[MacroRatesSource, ...] = (
    "treasury",
    "bis",
    "worldbank",
    "cme_fedwatch",
    "fred",
)
MACRO_RATES_FAMILIES: tuple[MacroRatesFamily, ...] = (
    "macro_indicators",
    "yield_curve",
    "fx_rates",
    "policy_rates",
    "credit_gaps",
    "fedwatch",
)
CRYPTO_DERIVATIVES_VENUES: tuple[CryptoDerivativesVenue, ...] = ("coingecko", "deribit")
CRYPTO_DERIVATIVES_DATA_TYPES: tuple[CryptoDerivativesDataType, ...] = (
    "spot",
    "global_market",
    "term_structure",
    "option_chain",
    "order_book",
)
CFTC_POSITIONING_REPORT_TYPES: tuple[CftcPositioningReportType, ...] = (
    "legacy_futures_only",
    "legacy_combined",
    "disaggregated_futures_only",
    "disaggregated_combined",
    "financial_futures",
)
OPTIONS_MONEYNESS_VALUES: tuple[OptionsMoneyness, ...] = (
    "all",
    "itm",
    "otm",
    "near_the_money",
)
MARKET_SENTIMENT_PROVIDER_KEY: MarketSentimentIndicator = "fear_greed"
MARKET_SENTIMENT_SOURCE_URL = "https://www.cnn.com/markets/fear-and-greed"

DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE = False
DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE = False
DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY = (
    "Phase 1 uses Digital Oracle provider wrappers; do not vendor "
    "digital-oracle or require yfinance."
)

EDGAR_CONTACT_EMAIL_SECRET = "edgar_contact_email"
EDGAR_CONTACT_EMAIL_MISSING_CODE = "digital_oracle_edgar_contact_secret_missing"
EDGAR_CONTACT_EMAIL_MISSING_MESSAGE = (
    "SEC EDGAR provider is not configured. Bind workflow package secret "
    f"{EDGAR_CONTACT_EMAIL_SECRET} before using "
    "signaldeck/digital-oracle/sec_filings_lookup."
)
FRED_API_KEY_SECRET = "fred_api_key"
FRED_API_KEY_MISSING_CODE = "digital_oracle_fred_secret_missing"
FRED_API_KEY_MISSING_MESSAGE = (
    "FRED macro rates source is not configured. Bind workflow package secret "
    f"{FRED_API_KEY_SECRET} before using the FRED source."
)
YFINANCE_OPTIONAL_DEPENDENCY = "yfinance"
YFINANCE_OPTIONAL_DEPENDENCY_MISSING_CODE = "digital_oracle_yfinance_missing"
YFINANCE_OPTIONAL_DEPENDENCY_MISSING_MESSAGE = (
    "YFinance options source is unavailable because the optional yfinance dependency is not "
    "installed."
)


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderConfig:
    prediction_markets_enabled: bool
    sec_filings_enabled: bool
    market_sentiment_enabled: bool
    macro_rates_enabled: bool
    crypto_derivatives_enabled: bool
    cftc_positioning_enabled: bool
    options_enabled: bool
    prediction_markets_default_item_limit: int
    sec_filings_default_item_limit: int
    macro_rates_default_item_limit: int
    crypto_derivatives_default_item_limit: int
    cftc_positioning_default_item_limit: int
    options_default_item_limit: int
    provider_timeout_seconds: float
    edgar_contact_email: str | None
    fred_api_key: str | None
    requires_vendored_package: bool = DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE
    requires_yfinance: bool = DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE
    provider_boundary: str = DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY

    @property
    def prediction_market_venues(self) -> tuple[PredictionMarketVenue, ...]:
        return PREDICTION_MARKET_VENUES

    @property
    def market_sentiment_indicator(self) -> MarketSentimentIndicator:
        return MARKET_SENTIMENT_PROVIDER_KEY

    @property
    def macro_rates_sources(self) -> tuple[MacroRatesSource, ...]:
        return MACRO_RATES_SOURCES

    @property
    def crypto_derivatives_venues(self) -> tuple[CryptoDerivativesVenue, ...]:
        return CRYPTO_DERIVATIVES_VENUES


def get_digital_oracle_provider_config(
    settings: DigitalOracleSettings | None = None,
) -> DigitalOracleProviderConfig:
    resolved_settings = settings or get_digital_oracle_settings()
    return DigitalOracleProviderConfig(
        prediction_markets_enabled=resolved_settings.prediction_markets_enabled,
        sec_filings_enabled=resolved_settings.sec_filings_enabled,
        market_sentiment_enabled=resolved_settings.market_sentiment_enabled,
        macro_rates_enabled=resolved_settings.macro_rates_enabled,
        crypto_derivatives_enabled=resolved_settings.crypto_derivatives_enabled,
        cftc_positioning_enabled=resolved_settings.cftc_positioning_enabled,
        options_enabled=resolved_settings.options_enabled,
        prediction_markets_default_item_limit=(
            resolved_settings.prediction_markets_default_item_limit
        ),
        sec_filings_default_item_limit=resolved_settings.sec_filings_default_item_limit,
        macro_rates_default_item_limit=resolved_settings.macro_rates_default_item_limit,
        crypto_derivatives_default_item_limit=(
            resolved_settings.crypto_derivatives_default_item_limit
        ),
        cftc_positioning_default_item_limit=(resolved_settings.cftc_positioning_default_item_limit),
        options_default_item_limit=resolved_settings.options_default_item_limit,
        provider_timeout_seconds=resolved_settings.provider_timeout_seconds,
        edgar_contact_email=None,
        fred_api_key=None,
    )


__all__ = [
    "DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY",
    "DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE",
    "DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE",
    "DigitalOracleSettings",
    "CRYPTO_DERIVATIVES_DATA_TYPES",
    "CRYPTO_DERIVATIVES_VENUES",
    "CFTC_POSITIONING_REPORT_TYPES",
    "EDGAR_CONTACT_EMAIL_MISSING_CODE",
    "EDGAR_CONTACT_EMAIL_MISSING_MESSAGE",
    "EDGAR_CONTACT_EMAIL_SECRET",
    "FRED_API_KEY_MISSING_CODE",
    "FRED_API_KEY_MISSING_MESSAGE",
    "FRED_API_KEY_SECRET",
    "MACRO_RATES_FAMILIES",
    "MACRO_RATES_SOURCES",
    "MARKET_SENTIMENT_PROVIDER_KEY",
    "MARKET_SENTIMENT_SOURCE_URL",
    "OPTIONS_MONEYNESS_VALUES",
    "PREDICTION_MARKET_VENUES",
    "YFINANCE_OPTIONAL_DEPENDENCY",
    "YFINANCE_OPTIONAL_DEPENDENCY_MISSING_CODE",
    "YFINANCE_OPTIONAL_DEPENDENCY_MISSING_MESSAGE",
    "DigitalOracleProviderConfig",
    "CftcPositioningReportType",
    "CryptoDerivativesDataType",
    "CryptoDerivativesVenue",
    "MacroRatesFamily",
    "MacroRatesSource",
    "MarketSentimentIndicator",
    "OptionsMoneyness",
    "PredictionMarketVenue",
    "get_digital_oracle_provider_config",
    "get_digital_oracle_settings",
    "reset_digital_oracle_settings_cache",
]
