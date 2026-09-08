"""Private operational identity for the bundled finance workspace extension."""

from __future__ import annotations

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"

FINANCE_WORKSPACE_DENIED_CODE = "agent_execution_access_denied"

FINANCE_WORKSPACE_DENIED_MESSAGES = {
    "signaldeck/finance/market_data_quote_lookup": (
        "Agent is not authorized to use signaldeck/finance/market_data_quote_lookup_"
    ),
    "signaldeck/finance/market_data_history_lookup": (
        "Agent is not authorized to use signaldeck/finance/market_data_history_lookup_"
    ),
    "signaldeck/finance/market_data_ohlcv_lookup": (
        "Agent is not authorized to use signaldeck/finance/market_data_ohlcv_lookup_"
    ),
    "signaldeck/finance/indicators_lookup": (
        "Agent is not authorized to use signaldeck/finance/indicators_lookup_"
    ),
    "signaldeck/finance/fundamentals_lookup": (
        "Agent is not authorized to use signaldeck/finance/fundamentals_lookup_"
    ),
    "signaldeck/finance/news_lookup": (
        "Agent is not authorized to use signaldeck/finance/news_lookup_"
    ),
    "signaldeck/finance/social_sentiment_lookup": (
        "Agent is not authorized to use signaldeck/finance/social_sentiment_lookup_"
    ),
    "signaldeck/finance/insider_data_lookup": (
        "Agent is not authorized to use signaldeck/finance/insider_data_lookup_"
    ),
    "signaldeck/finance/reports_lookup": (
        "Agent is not authorized to use signaldeck/finance/reports_lookup_"
    ),
}

FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS = (
    "signaldeck/finance/market_data_quote_lookup",
    "signaldeck/finance/market_data_history_lookup",
    "signaldeck/finance/market_data_ohlcv_lookup",
    "signaldeck/finance/indicators_lookup",
    "signaldeck/finance/fundamentals_lookup",
    "signaldeck/finance/news_lookup",
    "signaldeck/finance/social_sentiment_lookup",
    "signaldeck/finance/insider_data_lookup",
    "signaldeck/finance/reports_lookup",
)

FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_finance_market_data_quote_lookup",
    "signaldeck_finance_market_data_history_lookup",
    "signaldeck_finance_market_data_ohlcv_lookup",
    "signaldeck_finance_indicators_lookup",
    "signaldeck_finance_fundamentals_lookup",
    "signaldeck_finance_news_lookup",
    "signaldeck_finance_social_sentiment_lookup",
    "signaldeck_finance_insider_data_lookup",
    "signaldeck_finance_reports_lookup",
)

__all__ = [
    "FINANCE_WORKSPACE_DENIED_CODE",
    "FINANCE_WORKSPACE_DENIED_MESSAGES",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
]
