"""Non-sensitive deployment choices for the independent Finance providers."""

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class FinanceSettings(BaseSettings):
    quote_provider_timeout_seconds: float = Field(
        default=5.0, alias="QUOTE_PROVIDER_TIMEOUT", gt=0, allow_inf_nan=False
    )
    quote_provider_backend: Literal["yahoo", "deterministic"] = Field(
        default="yahoo", alias="QUOTE_PROVIDER_BACKEND"
    )
    news_provider_order: Annotated[list[str], NoDecode] = Field(
        default=["yahoo"], alias="FINANCE_NEWS_PROVIDER_ORDER"
    )
    global_news_queries: Annotated[list[str], NoDecode] = Field(
        default=["financial markets", "macro economy", "monetary policy"],
        alias="FINANCE_GLOBAL_NEWS_QUERIES",
    )
    global_news_lookback_days: int = Field(
        default=7, alias="FINANCE_GLOBAL_NEWS_LOOKBACK_DAYS", ge=1
    )
    reddit_subreddits: Annotated[list[str], NoDecode] = Field(
        default=["wallstreetbets", "stocks", "investing"], alias="FINANCE_REDDIT_SUBREDDITS"
    )
    reddit_retry_after_max_seconds: float = Field(
        default=2.0, alias="FINANCE_REDDIT_RETRY_AFTER_MAX_SECONDS", ge=0, allow_inf_nan=False
    )
    reddit_inter_request_delay_seconds: float = Field(
        default=0.0, alias="FINANCE_REDDIT_INTER_REQUEST_DELAY_SECONDS", ge=0, allow_inf_nan=False
    )
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="forbid", populate_by_name=True
    )

    @field_validator(
        "news_provider_order", "global_news_queries", "reddit_subreddits", mode="before"
    )
    @classmethod
    def split_lists(cls, value: str | list[str]) -> list[str]:
        return value.split(",") if isinstance(value, str) else value

    @field_validator("news_provider_order")
    @classmethod
    def normalize_providers(cls, value: list[str]) -> list[str]:
        providers = list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if not providers or set(providers) - {"yahoo", "alpha_vantage", "deterministic"}:
            raise ValueError(
                "FINANCE_NEWS_PROVIDER_ORDER requires yahoo, alpha_vantage or deterministic"
            )
        return providers

    @field_validator("global_news_queries", "reddit_subreddits")
    @classmethod
    def normalize_terms(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("quote_provider_backend", mode="before")
    @classmethod
    def normalize_backend(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def deterministic_is_a_test_choice(self) -> Self:
        if "deterministic" in self.news_provider_order and len(self.news_provider_order) != 1:
            raise ValueError("Deterministic test news cannot be a fallback for live providers")
        return self
