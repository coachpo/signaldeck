from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from plugin_runtime.formatting import decimal_to_string, parse_decimal_string, to_utc
from pydantic import BaseModel, ConfigDict, field_serializer


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


_RUNTIME_INPUT_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

type BrowserSafeErrorDetailValue = str | int | float | bool | None


def normalize_runtime_inputs(value: Any) -> dict[str, str]:
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError("Inputs must be an object")

    normalized_inputs: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ValueError("Input keys must be strings")

        key = raw_key.strip()
        if not key:
            raise ValueError("Input keys are required")
        if _RUNTIME_INPUT_KEY_RE.fullmatch(key) is None:
            raise ValueError(
                "Input keys must start with a letter or underscore and contain only letters, "
                "numbers, and underscores"
            )

        if raw_value is None:
            continue

        normalized_value = str(raw_value).strip()
        if not normalized_value:
            continue

        normalized_inputs[key] = normalized_value

    return normalized_inputs


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_common_values(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return decimal_to_string(value)
        if isinstance(value, datetime):
            return to_utc(value).isoformat().replace("+00:00", "Z")
        return value


class ErrorEnvelope(CamelModel):
    code: str
    message: str
    details: list[dict[str, BrowserSafeErrorDetailValue]]


class DecimalFieldMixin:
    @staticmethod
    def parse_decimal(value: object) -> Decimal:
        return parse_decimal_string(value)


def ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must include timezone information")
    return value.astimezone(timezone.utc)  # noqa: UP017
