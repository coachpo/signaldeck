from __future__ import annotations

import json
from datetime import date
from typing import cast

from oracle_plugin.config import CRYPTO_DERIVATIVES_DATA_TYPES, CRYPTO_DERIVATIVES_VENUES
from oracle_plugin.contracts import RuntimeToolError

CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME = (
    "signaldeck_digital_oracle_crypto_derivatives_lookup"
)

_MAX_ASSETS = 10
_MAX_DEPTH_LIMIT = 10
_MAX_EXPIRATIONS = 10
_MAX_ITEM_LIMIT = 50


def parse_crypto_derivatives_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(arguments_json)
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "assets",
            "venues",
            "dataTypes",
            "expirations",
            "includeOrderBook",
            "depthLimit",
            "itemLimit",
        },
    )
    include_order_book = _parse_optional_boolean(raw_arguments.get("includeOrderBook"))
    depth_limit = _parse_optional_integer(
        raw_arguments.get("depthLimit"),
        "depthLimit",
        maximum=_MAX_DEPTH_LIMIT,
    )
    if not include_order_book:
        depth_limit = None
    return {
        "assets": _parse_text_array(raw_arguments.get("assets"), "assets", maximum=_MAX_ASSETS),
        "venues": _parse_enum_array(
            raw_arguments.get("venues"),
            "venues",
            CRYPTO_DERIVATIVES_VENUES,
        ),
        "data_types": _parse_enum_array(
            raw_arguments.get("dataTypes"),
            "dataTypes",
            CRYPTO_DERIVATIVES_DATA_TYPES,
        ),
        "expirations": _parse_date_array(raw_arguments.get("expirations")),
        "include_order_book": include_order_book,
        "depth_limit": depth_limit,
        "item_limit": _parse_optional_integer(
            raw_arguments.get("itemLimit"),
            "itemLimit",
            maximum=_MAX_ITEM_LIMIT,
        ),
    }


def _parse_json_object(arguments_json: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "OpenAI response requested "
                f"{CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME} with invalid JSON arguments."
            ),
        ) from exc
    if not isinstance(raw_payload, dict):
        raise _invalid("arguments must be a JSON object.")
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(raw_arguments: dict[str, object], *, allowed_keys: set[str]) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise _invalid(f"arguments contained unsupported fields: {', '.join(unexpected_keys)}")


def _parse_enum_array[
    T: str
](value: object, field_name: str, allowed_values: tuple[T, ...],) -> tuple[T, ...] | None:
    values = _parse_text_array(value, field_name, maximum=len(allowed_values))
    if values is None:
        return None
    allowed = set(allowed_values)
    normalized: list[T] = []
    for value in values:
        candidate = cast(T, value.lower())
        if candidate not in allowed:
            raise _invalid(f"{field_name} must use: {', '.join(allowed_values)}.")
        normalized.append(candidate)
    return tuple(normalized)


def _parse_text_array(value: object, field_name: str, *, maximum: int) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _invalid(f"{field_name} must be an array of strings.")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in cast(list[object], value):
        if not isinstance(raw_item, str):
            raise _invalid(f"{field_name} must be an array of strings.")
        item = " ".join(raw_item.split()).strip()
        if not item:
            raise _invalid(f"{field_name} must not contain empty values.")
        dedupe_key = item.casefold()
        if dedupe_key not in seen:
            normalized.append(item.upper() if field_name == "assets" else item.lower())
            seen.add(dedupe_key)
    if not normalized:
        raise _invalid(f"{field_name} must contain at least one value.")
    if len(normalized) > maximum:
        raise _invalid(f"{field_name} must contain at most {maximum} values.")
    return tuple(normalized)


def _parse_date_array(value: object) -> tuple[date, ...] | None:
    raw_values = _parse_text_array(value, "expirations", maximum=_MAX_EXPIRATIONS)
    if raw_values is None:
        return None
    dates: list[date] = []
    for raw_value in raw_values:
        try:
            dates.append(date.fromisoformat(raw_value))
        except ValueError as exc:
            raise _invalid("expirations must be valid ISO dates.") from exc
    return tuple(dates)


def _parse_optional_boolean(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _invalid("includeOrderBook must be a boolean.")
    return value


def _parse_optional_integer(value: object, field_name: str, *, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f"{field_name} must be an integer.")
    if value < 1:
        raise _invalid(f"{field_name} must be at least 1.")
    if value > maximum:
        raise _invalid(f"{field_name} must be at most {maximum}.")
    return value


def _invalid(message: str) -> RuntimeToolError:
    return RuntimeToolError(
        code="agent_tool_call_invalid",
        message=f"{CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME} {message}",
    )


__all__ = [
    "CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME",
    "parse_crypto_derivatives_lookup_arguments",
]
