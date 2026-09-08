"""Private provider DTOs; no access to the host or its storage."""

from collections.abc import Callable
from dataclasses import dataclass, field

from plugin_runtime.common import CamelModel
from pydantic import Field, field_serializer


class RuntimeToolError(Exception):
    def __init__(self, *, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or []


@dataclass(frozen=True)
class RuntimeToolContext:
    session_factory: Callable
    quote_provider: object
    news_providers: tuple = ()
    social_sentiment_adapters: tuple = ()
    secrets: dict[str, str] = field(default_factory=dict)

    def resolve_secret_value(self, key: str):
        return self.secrets.get(key)


@dataclass(frozen=True)
class RuntimeToolSpec:
    key: str
    openai_function_name: str
    display_name: str
    description: str
    parameters_schema: dict
    guidance: str
    sort_order: int
    denied_code: str
    denied_message: str
    parser: Callable
    executor: Callable
    owner_extension_key: str | None = None


class WarningDetail(CamelModel):
    key: str
    value: str


class RuntimeToolWarning(CamelModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, str] = Field(default_factory=dict)

    @field_serializer("details")
    def records(self, value) -> list[WarningDetail]:
        return [WarningDetail(key=k, value=v) for k, v in sorted(value.items())]
