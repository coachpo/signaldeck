from __future__ import annotations

from datetime import date
from typing import cast

from oracle_plugin.config import (
    MACRO_RATES_FAMILIES,
    MACRO_RATES_SOURCES,
    MacroRatesFamily,
    MacroRatesSource,
)
from oracle_plugin.contracts import RuntimeToolContext, RuntimeToolSpec
from oracle_plugin.factory import (
    DigitalOracleProviderSecrets,
    create_digital_oracle_phase1_provider_bundle,
)
from oracle_plugin.mappers import map_macro_rates_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_macro_rates_parser import (
    MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
    parse_macro_rates_lookup_arguments,
)
from oracle_plugin.runtime_macro_rates_providers import (
    BisMacroRatesProvider,
    CmeFedWatchMacroRatesProvider,
    FredMacroRatesProvider,
    TreasuryMacroRatesProvider,
    WorldBankMacroRatesProvider,
    create_macro_rates_providers,
)
from oracle_plugin.runtime_types import MACRO_RATES_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import DigitalOracleMacroRatesQuery

MACRO_RATES_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
MACRO_RATES_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    MACRO_RATES_LOOKUP_TOOL_KEY
]

_MAX_ITEM_LIMIT = 50
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {"type": ["string", "null"], "minLength": 1, "maxLength": 200},
        "sources": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": list(MACRO_RATES_SOURCES)},
            "minItems": 1,
            "maxItems": len(MACRO_RATES_SOURCES),
        },
        "families": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": list(MACRO_RATES_FAMILIES)},
            "minItems": 1,
            "maxItems": len(MACRO_RATES_FAMILIES),
        },
        "seriesIds": {"type": ["array", "null"], "items": {"type": "string"}},
        "countries": {"type": ["array", "null"], "items": {"type": "string"}},
        "startDate": {"type": ["string", "null"]},
        "endDate": {"type": ["string", "null"]},
        "asOfDate": {"type": ["string", "null"]},
        "itemLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": _MAX_ITEM_LIMIT},
    },
    "required": [],
    "unevaluatedProperties": False,
}


def execute_macro_rates_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    result = DigitalOraclePhase1Service(
        provider_bundle=create_digital_oracle_phase1_provider_bundle(
            provider_secrets=DigitalOracleProviderSecrets(
                fred_api_key=context.resolve_secret_value("fred_api_key"),
            )
        ),
        macro_rates_providers=create_macro_rates_providers(),
    ).lookup_macro_rates(
        DigitalOracleMacroRatesQuery(
            query=cast(str | None, arguments["query"]),
            sources=cast(tuple[MacroRatesSource, ...] | None, arguments["sources"]),
            families=cast(tuple[MacroRatesFamily, ...] | None, arguments["families"]),
            series_ids=cast(tuple[str, ...] | None, arguments["series_ids"]),
            countries=cast(tuple[str, ...] | None, arguments["countries"]),
            start_date=cast(date | None, arguments["start_date"]),
            end_date=cast(date | None, arguments["end_date"]),
            as_of_date=cast(date | None, arguments["as_of_date"]),
            item_limit=cast(int | None, arguments["item_limit"]),
        )
    )
    return cast(
        dict[str, object],
        map_macro_rates_result(result).model_dump(mode="json", by_alias=True),
    )


MACRO_RATES_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MACRO_RATES_LOOKUP_TOOL_KEY,
    openai_function_name=MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Macro Rates Lookup",
    description="Read normalized macro, yield, policy-rate, and Fed-implied rates series.",
    parameters_schema=_PARAMETERS_SCHEMA,
    guidance=(
        "When you need macro or rates data, call signaldeck_digital_oracle_macro_rates_lookup. "
        "Use returned normalized series only, disclose warnings for missing sources, and never "
        "invent unavailable FRED, Treasury, BIS, World Bank, or CME FedWatch coverage."
    ),
    sort_order=89,
    denied_code=MACRO_RATES_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MACRO_RATES_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_macro_rates_lookup_arguments,
    executor=execute_macro_rates_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "BisMacroRatesProvider",
    "CmeFedWatchMacroRatesProvider",
    "FredMacroRatesProvider",
    "MACRO_RATES_LOOKUP_ACCESS_DENIED_CODE",
    "MACRO_RATES_LOOKUP_ACCESS_DENIED_MESSAGE",
    "MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME",
    "MACRO_RATES_LOOKUP_TOOL_SPEC",
    "TreasuryMacroRatesProvider",
    "WorldBankMacroRatesProvider",
    "create_macro_rates_providers",
    "execute_macro_rates_lookup",
    "parse_macro_rates_lookup_arguments",
]
