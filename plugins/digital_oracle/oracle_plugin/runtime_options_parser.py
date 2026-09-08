from __future__ import annotations

import json
from datetime import date
from typing import cast

from oracle_plugin.config import OPTIONS_MONEYNESS_VALUES, OptionsMoneyness
from oracle_plugin.contracts import RuntimeToolError

OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_digital_oracle_options_lookup"

_MAX_EXPIRATIONS = 10
_MAX_ITEM_LIMIT = 50
_MAX_SYMBOLS = 10


def parse_options_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(arguments_json)
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "expirations", "includeGreeks", "moneyness", "itemLimit"},
    )
    return {
        "symbols": _parse_symbols(raw_arguments.get("symbols")),
        "expirations": _parse_date_array(raw_arguments.get("expirations")),
        "include_greeks": _parse_optional_boolean(raw_arguments.get("includeGreeks")),
        "moneyness": _parse_moneyness(raw_arguments.get("moneyness")),
        "item_limit": _parse_optional_integer(raw_arguments.get("itemLimit"), "itemLimit"),
    }


def _parse_json_object(arguments_json: str) -> dict[str, object]:
    try:
        parsed_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "OpenAI response requested "
                f"{OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME} with invalid JSON arguments."
            ),
        ) from exc
    if not isinstance(parsed_payload, dict):
        raise _invalid("arguments must be a JSON object.")
    return cast(dict[str, object], parsed_payload)


def _reject_unexpected_keys(raw_arguments: dict[str, object], *, allowed_keys: set[str]) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise _invalid(f"arguments contained unsupported fields: {', '.join(unexpected_keys)}")


def _parse_symbols(value: object) -> tuple[str, ...]:
    values = _parse_text_array(value, "symbols", maximum=_MAX_SYMBOLS)
    if values is None:
        raise _invalid("symbols is required.")
    return tuple(symbol.upper() for symbol in values)


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
            normalized.append(item)
            seen.add(dedupe_key)
    if not normalized:
        raise _invalid(f"{field_name} must contain at least one value.")
    if len(normalized) > maximum:
        raise _invalid(f"{field_name} must contain at most {maximum} values.")
    return tuple(normalized)


def _parse_optional_boolean(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise _invalid("includeGreeks must be a boolean.")
    return value


def _parse_moneyness(value: object) -> OptionsMoneyness:
    if value is None:
        return "all"
    if not isinstance(value, str):
        raise _invalid("moneyness must be a string.")
    normalized = value.strip().lower()
    if normalized not in OPTIONS_MONEYNESS_VALUES:
        raise _invalid(f"moneyness must use: {', '.join(OPTIONS_MONEYNESS_VALUES)}.")
    return normalized


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
        message=f"{OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME} {message}",
    )


__all__ = ["OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME", "parse_options_lookup_arguments"]
