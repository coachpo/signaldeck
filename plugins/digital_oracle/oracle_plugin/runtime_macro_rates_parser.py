from __future__ import annotations

import json
from datetime import date
from typing import cast

from oracle_plugin.config import MACRO_RATES_FAMILIES, MACRO_RATES_SOURCES
from oracle_plugin.contracts import RuntimeToolError

MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_digital_oracle_macro_rates_lookup"

_MAX_ITEM_LIMIT = 50


def parse_macro_rates_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(arguments_json)
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "query",
            "sources",
            "families",
            "seriesIds",
            "countries",
            "startDate",
            "endDate",
            "asOfDate",
            "itemLimit",
        },
    )
    start_date = _parse_optional_date(raw_arguments.get("startDate"), "startDate")
    end_date = _parse_optional_date(raw_arguments.get("endDate"), "endDate")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise _invalid("startDate must be before or equal to endDate.")
    return {
        "query": _parse_optional_query(raw_arguments.get("query")),
        "sources": _parse_enum_array(raw_arguments.get("sources"), "sources", MACRO_RATES_SOURCES),
        "families": _parse_enum_array(
            raw_arguments.get("families"),
            "families",
            MACRO_RATES_FAMILIES,
        ),
        "series_ids": _parse_text_array(raw_arguments.get("seriesIds"), "seriesIds", upper=True),
        "countries": _parse_text_array(raw_arguments.get("countries"), "countries", upper=True),
        "start_date": start_date,
        "end_date": end_date,
        "as_of_date": _parse_optional_date(raw_arguments.get("asOfDate"), "asOfDate"),
        "item_limit": _parse_optional_integer(raw_arguments.get("itemLimit"), "itemLimit"),
    }


def _parse_json_object(arguments_json: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "OpenAI response requested "
                f"{MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME} with invalid JSON arguments."
            ),
        ) from exc
    if not isinstance(raw_payload, dict):
        raise _invalid("arguments must be a JSON object.")
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(raw_arguments: dict[str, object], *, allowed_keys: set[str]) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise _invalid(f"arguments contained unsupported fields: {', '.join(unexpected_keys)}")


def _parse_optional_query(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid("query must be a string.")
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise _invalid("query must not be empty.")
    if len(normalized) > 200:
        raise _invalid("query must be at most 200 characters.")
    return normalized


def _parse_enum_array[
    T: str
](value: object, field_name: str, allowed_values: tuple[T, ...],) -> tuple[T, ...] | None:
    values = _parse_text_array(value, field_name, upper=False)
    if values is None:
        return None
    allowed = set(allowed_values)
    normalized: list[T] = []
    seen: set[T] = set()
    for raw_value in values:
        candidate = cast(T, raw_value)
        if candidate not in allowed:
            raise _invalid(f"{field_name} must use: {', '.join(allowed_values)}.")
        if candidate not in seen:
            normalized.append(candidate)
            seen.add(candidate)
    return tuple(normalized)


def _parse_text_array(value: object, field_name: str, *, upper: bool) -> tuple[str, ...] | None:
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
        item = item.upper() if upper else item.lower()
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    if not normalized:
        raise _invalid(f"{field_name} must contain at least one value.")
    return tuple(normalized)


def _parse_optional_date(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(f"{field_name} must be a string date.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise _invalid(f"{field_name} must be a valid ISO date.") from exc


def _parse_optional_integer(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f"{field_name} must be an integer.")
    if value < 1:
        raise _invalid(f"{field_name} must be at least 1.")
    if value > _MAX_ITEM_LIMIT:
        raise _invalid(f"{field_name} must be at most {_MAX_ITEM_LIMIT}.")
    return value


def _invalid(message: str) -> RuntimeToolError:
    return RuntimeToolError(
        code="agent_tool_call_invalid",
        message=f"{MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME} {message}",
    )


__all__ = [
    "MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME",
    "parse_macro_rates_lookup_arguments",
]
