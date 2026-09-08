from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .config import (
    EDGAR_CONTACT_EMAIL_MISSING_CODE,
    EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
    EDGAR_CONTACT_EMAIL_SECRET,
    FRED_API_KEY_MISSING_CODE,
    FRED_API_KEY_MISSING_MESSAGE,
    FRED_API_KEY_SECRET,
    MARKET_SENTIMENT_PROVIDER_KEY,
    MARKET_SENTIMENT_SOURCE_URL,
    PREDICTION_MARKET_VENUES,
    YFINANCE_OPTIONAL_DEPENDENCY,
    YFINANCE_OPTIONAL_DEPENDENCY_MISSING_CODE,
    YFINANCE_OPTIONAL_DEPENDENCY_MISSING_MESSAGE,
    DigitalOracleProviderConfig,
    DigitalOracleSettings,
    MarketSentimentIndicator,
    PredictionMarketVenue,
    get_digital_oracle_provider_config,
)

_DIGITAL_ORACLE_PROVIDER_DISABLED_CODE = "digital_oracle_provider_disabled"

_PROVIDER_LABELS: Mapping[str, str] = {
    "bis": "BIS",
    "cftc": "CFTC COT",
    "cftc_positioning": "Digital Oracle CFTC positioning",
    "cme_fedwatch": "CME FedWatch",
    "coingecko": "CoinGecko",
    "crypto_derivatives": "Digital Oracle crypto derivatives",
    "deribit": "Deribit",
    "polymarket": "Polymarket",
    "fred": "FRED",
    "kalshi": "Kalshi",
    "edgar": "SEC EDGAR",
    "fear_greed": "Fear & Greed Index",
    "macro_rates": "Digital Oracle macro rates",
    "prediction_markets": "Digital Oracle prediction markets",
    "options": "Digital Oracle options",
    "market_sentiment": "Digital Oracle market sentiment",
    "treasury": "US Treasury",
    "worldbank": "World Bank",
    "yahoo": "Yahoo Finance",
    "yfinance": "YFinance",
}

_MACRO_RATE_PROVIDER_KEYS = ("treasury", "bis", "worldbank", "cme_fedwatch", "fred")
_CRYPTO_DERIVATIVES_PROVIDER_KEYS = ("deribit", "coingecko")
_CFTC_POSITIONING_PROVIDER_KEYS = ("cftc",)
_OPTIONS_PROVIDER_KEYS = ("yahoo",)


def _empty_failure_details() -> dict[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderFailure:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=_empty_failure_details)


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderDescriptor:
    key: str
    label: str
    timeout_seconds: float
    default_item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class PredictionMarketsProviderBundle:
    venues: tuple[PredictionMarketVenue, ...]
    providers: tuple[DigitalOracleProviderDescriptor, ...]
    default_item_limit: int


@dataclass(frozen=True, slots=True)
class SecFilingsProviderBundle:
    provider: DigitalOracleProviderDescriptor
    edgar_contact_email: str
    default_item_limit: int


@dataclass(frozen=True, slots=True)
class MarketSentimentProviderBundle:
    provider: DigitalOracleProviderDescriptor
    indicator: MarketSentimentIndicator
    source_url: str


@dataclass(frozen=True, slots=True)
class DigitalOracleSourceScopedProviderBundle:
    providers: tuple[DigitalOracleProviderDescriptor, ...]
    source_failures: tuple[DigitalOracleProviderFailure, ...]
    default_item_limit: int
    fred_api_key: str | None = None


@dataclass(frozen=True, slots=True)
class DigitalOraclePhase1ProviderBundle:
    prediction_markets: PredictionMarketsProviderBundle | DigitalOracleProviderFailure
    sec_filings: SecFilingsProviderBundle | DigitalOracleProviderFailure
    market_sentiment: MarketSentimentProviderBundle | DigitalOracleProviderFailure
    macro_rates: DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure
    crypto_derivatives: DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure
    cftc_positioning: DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure
    options: DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderSecrets:
    edgar_contact_email: str | None = None
    fred_api_key: str | None = None


def _disabled_failure(provider: str) -> DigitalOracleProviderFailure:
    label = _PROVIDER_LABELS[provider]
    return DigitalOracleProviderFailure(
        code=_DIGITAL_ORACLE_PROVIDER_DISABLED_CODE,
        message=f"{label} provider is disabled by backend configuration.",
        details={"provider": provider},
    )


def _missing_fred_key_failure() -> DigitalOracleProviderFailure:
    return DigitalOracleProviderFailure(
        code=FRED_API_KEY_MISSING_CODE,
        message=FRED_API_KEY_MISSING_MESSAGE,
        details={
            "provider": "fred",
            "secret": FRED_API_KEY_SECRET,
        },
    )


def _missing_yfinance_failure() -> DigitalOracleProviderFailure:
    return DigitalOracleProviderFailure(
        code=YFINANCE_OPTIONAL_DEPENDENCY_MISSING_CODE,
        message=YFINANCE_OPTIONAL_DEPENDENCY_MISSING_MESSAGE,
        details={
            "dependency": YFINANCE_OPTIONAL_DEPENDENCY,
            "provider": "yfinance",
        },
    )


def _optional_dependency_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _descriptor(
    *,
    key: str,
    config: DigitalOracleProviderConfig,
    default_item_limit: int | None = None,
) -> DigitalOracleProviderDescriptor:
    return DigitalOracleProviderDescriptor(
        key=key,
        label=_PROVIDER_LABELS[key],
        timeout_seconds=config.provider_timeout_seconds,
        default_item_limit=default_item_limit,
    )


def _source_scoped_bundle(
    *,
    enabled: bool,
    group_key: str,
    provider_keys: tuple[str, ...],
    config: DigitalOracleProviderConfig,
    default_item_limit: int,
    source_failures: tuple[DigitalOracleProviderFailure, ...] = (),
) -> DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure:
    if not enabled:
        return _disabled_failure(group_key)

    return DigitalOracleSourceScopedProviderBundle(
        providers=tuple(
            _descriptor(
                key=provider_key,
                config=config,
                default_item_limit=default_item_limit,
            )
            for provider_key in provider_keys
        ),
        source_failures=source_failures,
        default_item_limit=default_item_limit,
    )


def _with_fred_api_key(
    construction: DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure,
    fred_api_key: str | None,
) -> DigitalOracleSourceScopedProviderBundle | DigitalOracleProviderFailure:
    if isinstance(construction, DigitalOracleProviderFailure):
        return construction
    return DigitalOracleSourceScopedProviderBundle(
        providers=construction.providers,
        source_failures=construction.source_failures,
        default_item_limit=construction.default_item_limit,
        fred_api_key=fred_api_key,
    )


def _create_prediction_markets_provider_bundle(
    config: DigitalOracleProviderConfig,
) -> PredictionMarketsProviderBundle | DigitalOracleProviderFailure:
    if not config.prediction_markets_enabled:
        return _disabled_failure("prediction_markets")

    providers = tuple(
        _descriptor(
            key=venue,
            config=config,
            default_item_limit=config.prediction_markets_default_item_limit,
        )
        for venue in PREDICTION_MARKET_VENUES
    )
    return PredictionMarketsProviderBundle(
        venues=PREDICTION_MARKET_VENUES,
        providers=providers,
        default_item_limit=config.prediction_markets_default_item_limit,
    )


def _create_sec_filings_provider(
    config: DigitalOracleProviderConfig,
) -> SecFilingsProviderBundle | DigitalOracleProviderFailure:
    if not config.sec_filings_enabled:
        return _disabled_failure("edgar")
    if config.edgar_contact_email is None:
        return DigitalOracleProviderFailure(
            code=EDGAR_CONTACT_EMAIL_MISSING_CODE,
            message=EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            details={
                "provider": "edgar",
                "secret": EDGAR_CONTACT_EMAIL_SECRET,
            },
        )

    return SecFilingsProviderBundle(
        provider=_descriptor(
            key="edgar",
            config=config,
            default_item_limit=config.sec_filings_default_item_limit,
        ),
        edgar_contact_email=config.edgar_contact_email,
        default_item_limit=config.sec_filings_default_item_limit,
    )


def _create_market_sentiment_provider(
    config: DigitalOracleProviderConfig,
) -> MarketSentimentProviderBundle | DigitalOracleProviderFailure:
    if not config.market_sentiment_enabled:
        return _disabled_failure("market_sentiment")

    return MarketSentimentProviderBundle(
        provider=_descriptor(key=MARKET_SENTIMENT_PROVIDER_KEY, config=config),
        indicator=MARKET_SENTIMENT_PROVIDER_KEY,
        source_url=MARKET_SENTIMENT_SOURCE_URL,
    )


def create_prediction_markets_provider_bundle(
    settings: DigitalOracleSettings | None = None,
) -> PredictionMarketsProviderBundle | DigitalOracleProviderFailure:
    config = get_digital_oracle_provider_config(settings)
    return _create_prediction_markets_provider_bundle(config)


def create_sec_filings_provider(
    settings: DigitalOracleSettings | None = None,
    provider_secrets: DigitalOracleProviderSecrets | None = None,
) -> SecFilingsProviderBundle | DigitalOracleProviderFailure:
    config = _config_with_provider_secrets(
        get_digital_oracle_provider_config(settings),
        provider_secrets,
    )
    return _create_sec_filings_provider(config)


def create_market_sentiment_provider(
    settings: DigitalOracleSettings | None = None,
) -> MarketSentimentProviderBundle | DigitalOracleProviderFailure:
    config = get_digital_oracle_provider_config(settings)
    return _create_market_sentiment_provider(config)


def create_digital_oracle_phase1_provider_bundle(
    settings: DigitalOracleSettings | None = None,
    provider_secrets: DigitalOracleProviderSecrets | None = None,
) -> DigitalOraclePhase1ProviderBundle:
    config = _config_with_provider_secrets(
        get_digital_oracle_provider_config(settings),
        provider_secrets,
    )
    return DigitalOraclePhase1ProviderBundle(
        prediction_markets=_create_prediction_markets_provider_bundle(config),
        sec_filings=_create_sec_filings_provider(config),
        market_sentiment=_create_market_sentiment_provider(config),
        macro_rates=_with_fred_api_key(
            _source_scoped_bundle(
                enabled=config.macro_rates_enabled,
                group_key="macro_rates",
                provider_keys=_MACRO_RATE_PROVIDER_KEYS,
                config=config,
                default_item_limit=config.macro_rates_default_item_limit,
                source_failures=(
                    () if config.fred_api_key is not None else (_missing_fred_key_failure(),)
                ),
            ),
            config.fred_api_key,
        ),
        crypto_derivatives=_source_scoped_bundle(
            enabled=config.crypto_derivatives_enabled,
            group_key="crypto_derivatives",
            provider_keys=_CRYPTO_DERIVATIVES_PROVIDER_KEYS,
            config=config,
            default_item_limit=config.crypto_derivatives_default_item_limit,
        ),
        cftc_positioning=_source_scoped_bundle(
            enabled=config.cftc_positioning_enabled,
            group_key="cftc_positioning",
            provider_keys=_CFTC_POSITIONING_PROVIDER_KEYS,
            config=config,
            default_item_limit=config.cftc_positioning_default_item_limit,
        ),
        options=_source_scoped_bundle(
            enabled=config.options_enabled,
            group_key="options",
            provider_keys=_OPTIONS_PROVIDER_KEYS,
            config=config,
            default_item_limit=config.options_default_item_limit,
            source_failures=(
                ()
                if _optional_dependency_available(YFINANCE_OPTIONAL_DEPENDENCY)
                else (_missing_yfinance_failure(),)
            ),
        ),
    )


def _config_with_provider_secrets(
    config: DigitalOracleProviderConfig,
    provider_secrets: DigitalOracleProviderSecrets | None,
) -> DigitalOracleProviderConfig:
    if provider_secrets is None:
        return config
    return replace(
        config,
        edgar_contact_email=provider_secrets.edgar_contact_email,
        fred_api_key=provider_secrets.fred_api_key,
    )


__all__ = [
    "DigitalOraclePhase1ProviderBundle",
    "DigitalOracleProviderSecrets",
    "DigitalOracleProviderDescriptor",
    "DigitalOracleProviderFailure",
    "DigitalOracleSourceScopedProviderBundle",
    "MarketSentimentProviderBundle",
    "PredictionMarketsProviderBundle",
    "SecFilingsProviderBundle",
    "create_digital_oracle_phase1_provider_bundle",
    "create_market_sentiment_provider",
    "create_prediction_markets_provider_bundle",
    "create_sec_filings_provider",
]
