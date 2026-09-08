from __future__ import annotations

from functools import lru_cache
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DigitalOracleSettings(BaseSettings):
    prediction_markets_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED",
    )
    sec_filings_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_SEC_FILINGS_ENABLED",
    )
    market_sentiment_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_MARKET_SENTIMENT_ENABLED",
    )
    macro_rates_enabled: bool = Field(default=True, alias="DIGITAL_ORACLE_MACRO_RATES_ENABLED")
    crypto_derivatives_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED",
    )
    cftc_positioning_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED",
    )
    options_enabled: bool = Field(default=True, alias="DIGITAL_ORACLE_OPTIONS_ENABLED")
    prediction_markets_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=20,
    )
    sec_filings_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    macro_rates_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    crypto_derivatives_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    cftc_positioning_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    options_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    provider_timeout_seconds: float = Field(default=5.0, alias="DIGITAL_ORACLE_PROVIDER_TIMEOUT")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_digital_oracle_settings() -> DigitalOracleSettings:
    return DigitalOracleSettings()


def reset_digital_oracle_settings_cache() -> None:
    get_digital_oracle_settings.cache_clear()


__all__ = [
    "DigitalOracleSettings",
    "get_digital_oracle_settings",
    "reset_digital_oracle_settings_cache",
]
