from __future__ import annotations

from datetime import date
from typing import cast

from oracle_plugin.config import CFTC_POSITIONING_REPORT_TYPES, CftcPositioningReportType
from oracle_plugin.contracts import RuntimeToolContext, RuntimeToolSpec
from oracle_plugin.mappers import map_cftc_positioning_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_cftc_positioning_parser import (
    CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
    parse_cftc_positioning_lookup_arguments,
)
from oracle_plugin.runtime_cftc_positioning_providers import (
    CftcCotPositioningProvider,
    create_cftc_positioning_providers,
)
from oracle_plugin.runtime_types import CFTC_POSITIONING_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import DigitalOracleCftcPositioningQuery

CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    CFTC_POSITIONING_LOOKUP_TOOL_KEY
]

_MAX_ITEM_LIMIT = 50
_MAX_MARKETS = 10
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "markets": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MAX_MARKETS,
        },
        "reportTypes": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": list(CFTC_POSITIONING_REPORT_TYPES)},
            "minItems": 1,
            "maxItems": len(CFTC_POSITIONING_REPORT_TYPES),
        },
        "startDate": {"type": ["string", "null"]},
        "endDate": {"type": ["string", "null"]},
        "itemLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": _MAX_ITEM_LIMIT},
    },
    "required": [],
    "unevaluatedProperties": False,
}


def execute_cftc_positioning_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    result = DigitalOraclePhase1Service(
        cftc_positioning_providers=create_cftc_positioning_providers(),
    ).lookup_cftc_positioning(
        DigitalOracleCftcPositioningQuery(
            markets=cast(tuple[str, ...] | None, arguments["markets"]),
            report_types=cast(
                tuple[CftcPositioningReportType, ...] | None,
                arguments["report_types"],
            ),
            start_date=cast(date | None, arguments["start_date"]),
            end_date=cast(date | None, arguments["end_date"]),
            item_limit=cast(int | None, arguments["item_limit"]),
        )
    )
    return cast(
        dict[str, object],
        map_cftc_positioning_result(result).model_dump(mode="json", by_alias=True),
    )


CFTC_POSITIONING_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    openai_function_name=CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="CFTC Positioning Lookup",
    description="Read normalized CFTC Commitment of Traders positioning reports.",
    parameters_schema=_PARAMETERS_SCHEMA,
    guidance=(
        "When you need CFTC Commitment of Traders positioning, call "
        "signaldeck_digital_oracle_cftc_positioning_lookup. Use returned normalized reports "
        "only, disclose warnings for missing or malformed markets, and never expose raw CFTC rows."
    ),
    sort_order=91,
    denied_code=CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_cftc_positioning_lookup_arguments,
    executor=execute_cftc_positioning_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_CODE",
    "CFTC_POSITIONING_LOOKUP_ACCESS_DENIED_MESSAGE",
    "CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME",
    "CFTC_POSITIONING_LOOKUP_TOOL_SPEC",
    "CftcCotPositioningProvider",
    "create_cftc_positioning_providers",
    "execute_cftc_positioning_lookup",
    "parse_cftc_positioning_lookup_arguments",
]
