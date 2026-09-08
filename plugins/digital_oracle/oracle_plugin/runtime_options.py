from __future__ import annotations

from datetime import date
from typing import cast

from oracle_plugin.config import OPTIONS_MONEYNESS_VALUES, OptionsMoneyness
from oracle_plugin.contracts import RuntimeToolContext, RuntimeToolSpec
from oracle_plugin.mappers import map_options_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_options_parser import (
    OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
    parse_options_lookup_arguments,
)
from oracle_plugin.runtime_options_providers import YahooOptionsProvider, create_options_providers
from oracle_plugin.runtime_types import OPTIONS_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import DigitalOracleOptionsQuery

OPTIONS_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
OPTIONS_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[OPTIONS_LOOKUP_TOOL_KEY]

_MAX_EXPIRATIONS = 10
_MAX_ITEM_LIMIT = 50
_MAX_SYMBOLS = 10
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MAX_SYMBOLS,
        },
        "expirations": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MAX_EXPIRATIONS,
        },
        "includeGreeks": {"type": ["boolean", "null"]},
        "moneyness": {"type": ["string", "null"], "enum": [*OPTIONS_MONEYNESS_VALUES, None]},
        "itemLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": _MAX_ITEM_LIMIT},
    },
    "required": ["symbols"],
    "unevaluatedProperties": False,
}


def execute_options_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    result = DigitalOraclePhase1Service(
        options_providers=create_options_providers(),
    ).lookup_options(
        DigitalOracleOptionsQuery(
            symbols=cast(tuple[str, ...], arguments["symbols"]),
            expirations=cast(tuple[date, ...] | None, arguments["expirations"]),
            include_greeks=cast(bool, arguments["include_greeks"]),
            moneyness=cast(OptionsMoneyness, arguments["moneyness"]),
            item_limit=cast(int | None, arguments["item_limit"]),
        )
    )
    return cast(
        dict[str, object],
        map_options_result(result).model_dump(mode="json", by_alias=True),
    )


OPTIONS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=OPTIONS_LOOKUP_TOOL_KEY,
    openai_function_name=OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Options Lookup",
    description="Read normalized Yahoo option-chain data through an optional yfinance adapter.",
    parameters_schema=_PARAMETERS_SCHEMA,
    guidance=(
        "When you need equity option chains, call signaldeck_digital_oracle_options_lookup. "
        "Use returned normalized Yahoo calls and puts only, disclose provider warnings, and "
        "never expose raw provider payloads."
    ),
    sort_order=92,
    denied_code=OPTIONS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=OPTIONS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_options_lookup_arguments,
    executor=execute_options_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "OPTIONS_LOOKUP_ACCESS_DENIED_CODE",
    "OPTIONS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME",
    "OPTIONS_LOOKUP_TOOL_SPEC",
    "YahooOptionsProvider",
    "create_options_providers",
    "execute_options_lookup",
    "parse_options_lookup_arguments",
]
