from __future__ import annotations

from oracle_plugin.contracts import RuntimeToolSpec
from oracle_plugin.runtime_cftc_positioning import CFTC_POSITIONING_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_crypto_derivatives import CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_macro_rates import MACRO_RATES_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_market_sentiment import MARKET_SENTIMENT_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_options import OPTIONS_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_prediction_markets import PREDICTION_MARKETS_LOOKUP_TOOL_SPEC
from oracle_plugin.runtime_sec_filings import SEC_FILINGS_LOOKUP_TOOL_SPEC

DIGITAL_ORACLE_RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...] = (
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
    MACRO_RATES_LOOKUP_TOOL_SPEC,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC,
    CFTC_POSITIONING_LOOKUP_TOOL_SPEC,
    OPTIONS_LOOKUP_TOOL_SPEC,
)


def register() -> tuple[RuntimeToolSpec, ...]:
    return DIGITAL_ORACLE_RUNTIME_TOOL_SPECS


__all__ = [
    "CFTC_POSITIONING_LOOKUP_TOOL_SPEC",
    "CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC",
    "DIGITAL_ORACLE_RUNTIME_TOOL_SPECS",
    "MACRO_RATES_LOOKUP_TOOL_SPEC",
    "OPTIONS_LOOKUP_TOOL_SPEC",
    "register",
]
