from __future__ import annotations

from datetime import date
from typing import cast

from oracle_plugin.config import (
    CRYPTO_DERIVATIVES_DATA_TYPES,
    CRYPTO_DERIVATIVES_VENUES,
    CryptoDerivativesDataType,
    CryptoDerivativesVenue,
)
from oracle_plugin.contracts import RuntimeToolContext, RuntimeToolSpec
from oracle_plugin.mappers import map_crypto_derivatives_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_crypto_derivatives_parser import (
    CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME,
    parse_crypto_derivatives_lookup_arguments,
)
from oracle_plugin.runtime_crypto_derivatives_providers import (
    CoinGeckoCryptoDerivativesProvider,
    DeribitCryptoDerivativesProvider,
    create_crypto_derivatives_providers,
)
from oracle_plugin.runtime_types import CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import DigitalOracleCryptoDerivativesQuery

CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
]

_MAX_ASSETS = 10
_MAX_DEPTH_LIMIT = 10
_MAX_EXPIRATIONS = 10
_MAX_ITEM_LIMIT = 50
_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "assets": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MAX_ASSETS,
        },
        "venues": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": list(CRYPTO_DERIVATIVES_VENUES)},
            "minItems": 1,
            "maxItems": len(CRYPTO_DERIVATIVES_VENUES),
        },
        "dataTypes": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": list(CRYPTO_DERIVATIVES_DATA_TYPES)},
            "minItems": 1,
            "maxItems": len(CRYPTO_DERIVATIVES_DATA_TYPES),
        },
        "expirations": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MAX_EXPIRATIONS,
        },
        "includeOrderBook": {"type": ["boolean", "null"]},
        "depthLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": _MAX_DEPTH_LIMIT},
        "itemLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": _MAX_ITEM_LIMIT},
    },
    "required": [],
    "unevaluatedProperties": False,
}


def execute_crypto_derivatives_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    result = DigitalOraclePhase1Service(
        crypto_derivatives_providers=create_crypto_derivatives_providers(),
    ).lookup_crypto_derivatives(
        DigitalOracleCryptoDerivativesQuery(
            assets=cast(tuple[str, ...] | None, arguments["assets"]),
            venues=cast(tuple[CryptoDerivativesVenue, ...] | None, arguments["venues"]),
            data_types=cast(
                tuple[CryptoDerivativesDataType, ...] | None,
                arguments["data_types"],
            ),
            expirations=cast(tuple[date, ...] | None, arguments["expirations"]),
            include_order_book=cast(bool, arguments["include_order_book"]),
            depth_limit=cast(int | None, arguments["depth_limit"]),
            item_limit=cast(int | None, arguments["item_limit"]),
        )
    )
    return cast(
        dict[str, object],
        map_crypto_derivatives_result(result).model_dump(mode="json", by_alias=True),
    )


CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    openai_function_name=CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Crypto Derivatives Lookup",
    description="Read normalized crypto spot, term-structure, option-chain, and orderbook data.",
    parameters_schema=_PARAMETERS_SCHEMA,
    guidance=(
        "When you need crypto derivatives data, call "
        "signaldeck_digital_oracle_crypto_derivatives_lookup. Use returned normalized "
        "CoinGecko and Deribit records only, disclose provider warnings, and never "
        "expose raw payloads."
    ),
    sort_order=90,
    denied_code=CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_crypto_derivatives_lookup_arguments,
    executor=execute_crypto_derivatives_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_CODE",
    "CRYPTO_DERIVATIVES_LOOKUP_ACCESS_DENIED_MESSAGE",
    "CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME",
    "CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC",
    "CoinGeckoCryptoDerivativesProvider",
    "DeribitCryptoDerivativesProvider",
    "create_crypto_derivatives_providers",
    "execute_crypto_derivatives_lookup",
    "parse_crypto_derivatives_lookup_arguments",
]
