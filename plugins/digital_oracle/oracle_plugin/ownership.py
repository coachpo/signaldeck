"""Private operational identity for the bundled Digital Oracle Runtime extension."""

from __future__ import annotations

DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle"

DIGITAL_ORACLE_DENIED_CODE = "agent_execution_access_denied"

DIGITAL_ORACLE_DENIED_MESSAGES = {
    "signaldeck/digital-oracle/prediction_markets_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/prediction_markets_lookup."
    ),
    "signaldeck/digital-oracle/sec_filings_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/sec_filings_lookup."
    ),
    "signaldeck/digital-oracle/market_sentiment_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/market_sentiment_lookup."
    ),
    "signaldeck/digital-oracle/macro_rates_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/macro_rates_lookup."
    ),
    "signaldeck/digital-oracle/crypto_derivatives_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/crypto_derivatives_lookup."
    ),
    "signaldeck/digital-oracle/cftc_positioning_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/cftc_positioning_lookup."
    ),
    "signaldeck/digital-oracle/options_lookup": (
        "Agent is not authorized to use signaldeck/digital-oracle/options_lookup."
    ),
}

DIGITAL_ORACLE_RUNTIME_TOOL_KEYS = (
    "signaldeck/digital-oracle/prediction_markets_lookup",
    "signaldeck/digital-oracle/sec_filings_lookup",
    "signaldeck/digital-oracle/market_sentiment_lookup",
    "signaldeck/digital-oracle/macro_rates_lookup",
    "signaldeck/digital-oracle/crypto_derivatives_lookup",
    "signaldeck/digital-oracle/cftc_positioning_lookup",
    "signaldeck/digital-oracle/options_lookup",
)
DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_digital_oracle_prediction_markets_lookup",
    "signaldeck_digital_oracle_sec_filings_lookup",
    "signaldeck_digital_oracle_market_sentiment_lookup",
    "signaldeck_digital_oracle_macro_rates_lookup",
    "signaldeck_digital_oracle_crypto_derivatives_lookup",
    "signaldeck_digital_oracle_cftc_positioning_lookup",
    "signaldeck_digital_oracle_options_lookup",
)

__all__ = [
    "DIGITAL_ORACLE_DENIED_CODE",
    "DIGITAL_ORACLE_DENIED_MESSAGES",
    "DIGITAL_ORACLE_EXTENSION_KEY",
    "DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES",
    "DIGITAL_ORACLE_RUNTIME_TOOL_KEYS",
]
