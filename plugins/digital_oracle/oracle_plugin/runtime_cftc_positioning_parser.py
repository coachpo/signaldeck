from __future__ import annotations

import json
from datetime import date
from typing import cast

from oracle_plugin.config import CFTC_POSITIONING_REPORT_TYPES
from oracle_plugin.contracts import RuntimeToolError

CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_digital_oracle_cftc_positioning_lookup"

_MAX_ITEM_LIMIT = 50
_MAX_MARKETS = 10


def parse_cftc_positioning_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(arguments_json)
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"markets", "reportTypes", "startDate", "endDate", "itemLimit"},
    )
    start_date = _parse_optional_date(raw_arguments.get("startDate"), "startDate")
    end_date = _parse_optional_date(raw_arguments.get("endDate"), "endDate")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise _invalid("startDate must be before or equal to endDate.")
    return {
        "markets": _parse_text_array(raw_arguments.get("markets"), "markets"),
        "report_types": _parse_enum_array(raw_arguments.get("reportTypes"), "reportTypes"),
        "start_date": start_date,
        "end_date": end_date,
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
                f"{CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME} with invalid JSON arguments."
            ),
        ) from exc
    if not isinstance(raw_payload, dict):
        raise _invalid("arguments must be a JSON object.")
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(raw_arguments: dict[str, object], *, allowed_keys: set[str]) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise _invalid(f"arguments contained unsupported fields: {', '.join(unexpected_keys)}")


def _parse_enum_array(value: object, field_name: str) -> tuple[str, ...] | None:
    values = _parse_text_array(value, field_name)
    if values is None:
        return None
    allowed = set(CFTC_POSITIONING_REPORT_TYPES)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = value.lower()
        if candidate not in allowed:
            raise _invalid(f"{field_name} must use: {', '.join(CFTC_POSITIONING_REPORT_TYPES)}.")
        if candidate not in seen:
            normalized.append(candidate)
            seen.add(candidate)
    return tuple(normalized)


def _parse_text_array(value: object, field_name: str) -> tuple[str, ...] | None:
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
            normalized.append(item)
            seen.add(dedupe_key)
    if not normalized:
        raise _invalid(f"{field_name} must contain at least one value.")
    if len(normalized) > _MAX_MARKETS:
        raise _invalid(f"{field_name} must contain at most {_MAX_MARKETS} values.")
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
        message=f"{CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME} {message}",
    )


__all__ = [
    "CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME",
    "parse_cftc_positioning_lookup_arguments",
]
