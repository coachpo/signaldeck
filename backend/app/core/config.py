from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+psycopg://signaldeck:signaldeck@localhost:25432/signaldeck"
DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY = "signaldeck-agent-platform-dev-key"
PRODUCTION_RUNTIME_MODES = {"production", "prod", "staging"}
PLACEHOLDER_AGENT_PLATFORM_ENCRYPTION_KEYS = {
    DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
    "change-me",
    "changeme",
}
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    temporal_address: str = Field(default="127.0.0.1:7233", alias="TEMPORAL_ADDRESS")
    artifact_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".data" / "artifacts"),
        alias="SIGNALDECK_ARTIFACT_DIR",
    )
    core_artifact_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".data" / "core"),
        alias="SIGNALDECK_CORE_ARTIFACT_DIR",
    )
    runtime_mode: Literal["local", "development", "test", "staging", "production", "prod"] = Field(
        default="local",
        alias="SIGNALDECK_RUNTIME_MODE",
    )
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
    )
    agent_platform_encryption_key: str = Field(
        default=DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
        alias="AGENT_PLATFORM_ENCRYPTION_KEY",
    )
    api_token: str | None = Field(default=None, alias="SIGNALDECK_API_TOKEN")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        alias="CORS_ALLOWED_ORIGINS",
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "cors_allowed_origins",
        mode="before",
    )
    @classmethod
    def split_string_lists(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("api_token", mode="before")
    @classmethod
    def normalize_api_token(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("runtime_mode", mode="before")
    @classmethod
    def normalize_runtime_mode(cls, value: object) -> object:
        if value is None:
            return value
        return str(value).strip().lower()

    @field_validator("agent_platform_encryption_key", mode="before")
    @classmethod
    def normalize_agent_platform_encryption_key(cls, value: object) -> str:
        return str(value).strip() if value is not None else ""

    @model_validator(mode="after")
    def validate_production_runtime_config(self) -> Settings:
        if self.runtime_mode not in PRODUCTION_RUNTIME_MODES:
            return self

        if "database_url" not in self.model_fields_set or self.database_url == DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL must be explicitly configured in production runtime mode"
            )

        if (
            "agent_platform_encryption_key" not in self.model_fields_set
            or self.agent_platform_encryption_key in PLACEHOLDER_AGENT_PLATFORM_ENCRYPTION_KEYS
        ):
            message = (
                "AGENT_PLATFORM_ENCRYPTION_KEY must be explicitly configured to a non-placeholder "
                "value in production runtime mode"
            )
            raise ValueError(message)

        if self.api_token is None:
            logger.warning(
                "SIGNALDECK_API_TOKEN is not configured in production runtime mode; "
                "relying on reverse-proxy authentication."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
