from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import cast

from finance_plugin.contracts import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from finance_plugin.ownership import (
    FINANCE_WORKSPACE_DENIED_CODE,
    FINANCE_WORKSPACE_DENIED_MESSAGES,
    FINANCE_WORKSPACE_EXTENSION_KEY,
)
from finance_plugin.providers.news_provider import NewsProvider, NewsScope
from finance_plugin.runtime_types import (
    FUNDAMENTALS_LOOKUP_TOOL_KEY,
    INDICATORS_LOOKUP_TOOL_KEY,
    INSIDER_DATA_LOOKUP_TOOL_KEY,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    NEWS_LOOKUP_TOOL_KEY,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    RuntimeFundamentalsLookupResult,
    RuntimeHistoryLookupResult,
    RuntimeIndicatorLookupResult,
    RuntimeInsiderDataLookupResult,
    RuntimeNewsLookupResult,
    RuntimeOhlcvLookupResult,
    RuntimeQuoteLookupResult,
    RuntimeSocialSentimentLookupResult,
)
from finance_plugin.schemas.market_data import MarketHistorySeriesRead, MarketQuoteRead
from finance_plugin.services.market_data_service import (
    MarketDataService,
    MarketIndicatorSelection,
    QuoteProvider,
    QuoteProviderError,
)
from plugin_runtime.formatting import normalize_symbol, to_utc

MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_market_data_quote_lookup"
MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_market_data_history_lookup"
MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_market_data_ohlcv_lookup"
INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_indicators_lookup"
FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_fundamentals_lookup"
NEWS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_news_lookup"
SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_social_sentiment_lookup"
INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_insider_data_lookup"

MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
INDICATORS_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
FUNDAMENTALS_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
NEWS_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
INSIDER_DATA_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY
]
MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY
]

_QUOTE_SYMBOL_LIMIT = 10
_MARKET_DATA_SYMBOL_LIMIT = 5
_HISTORY_SYMBOL_LIMIT = 5
_HISTORY_DEFAULT_POINT_LIMIT = 120
_HISTORY_MAX_POINT_LIMIT = 250
_HISTORY_RANGES = {"1mo", "3mo", "ytd", "1y", "max"}
_OHLCV_DEFAULT_ROW_LIMIT = 250
_OHLCV_MAX_ROW_LIMIT = 500
_INDICATOR_DEFAULT_ROW_LIMIT = 250
_INDICATOR_MAX_ROW_LIMIT = 500
_INDICATOR_MAX_SELECTIONS = 24
_FUNDAMENTALS_DEFAULT_STATEMENT_LIMIT = 6
_FUNDAMENTALS_MAX_STATEMENT_LIMIT = 12
_NEWS_DEFAULT_ITEM_LIMIT = 25
_NEWS_MAX_ITEM_LIMIT = 50
_NEWS_SCOPES = {"symbol", "market", "global"}
_SOCIAL_SENTIMENT_DEFAULT_ITEM_LIMIT = 25
_SOCIAL_SENTIMENT_MAX_ITEM_LIMIT = 50
_SOCIAL_SENTIMENT_SOURCES = {"reddit", "stocktwits"}
_INSIDER_DEFAULT_TRANSACTION_LIMIT = 50
_INSIDER_MAX_TRANSACTION_LIMIT = 100
_FINANCIAL_STATEMENT_TYPES = {"income_statement", "balance_sheet", "cash_flow"}
_FINANCIAL_STATEMENT_PERIODS = {"annual", "quarterly", "trailing_twelve_months"}
_FUNDAMENTAL_METRIC_NAMES = {
    "beta",
    "current_ratio",
    "debt_to_equity",
    "dividend_yield",
    "earnings_growth",
    "enterprise_value",
    "ev_to_ebitda",
    "forward_pe",
    "free_cash_flow_margin",
    "gross_margin",
    "market_cap",
    "net_margin",
    "operating_margin",
    "price_to_book",
    "price_to_sales",
    "return_on_assets",
    "return_on_equity",
    "revenue_growth",
    "trailing_pe",
}
_INDICATOR_TYPES = {
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger_bands",
    "atr",
    "vwma",
}
MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY
]
INDICATORS_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    INDICATORS_LOOKUP_TOOL_KEY
]
FUNDAMENTALS_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    FUNDAMENTALS_LOOKUP_TOOL_KEY
]
NEWS_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[NEWS_LOOKUP_TOOL_KEY]
SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY
]
INSIDER_DATA_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    INSIDER_DATA_LOOKUP_TOOL_KEY
]

_QUOTE_LOOKUP_DESCRIPTION = "Read trusted market quote snapshots for up to 10 symbols."
_QUOTE_LOOKUP_GUIDANCE = (
    "When you need current or delayed market quotes, call the "
    "signaldeck_finance_market_data_quote_lookup tool instead of inventing prices. "
    "Disclose returned warnings or empty payloads as "
    "data quality or provider limitations."
)
_QUOTE_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _QUOTE_SYMBOL_LIMIT,
        },
    },
    "required": ["symbols"],
    "unevaluatedProperties": False,
}

_HISTORY_LOOKUP_DESCRIPTION = (
    "Read trusted historical close-price series for up to 5 " "symbols and a bounded point count."
)
_HISTORY_LOOKUP_GUIDANCE = (
    "When you need historical market prices, call the "
    "signaldeck_finance_market_data_history_lookup tool instead of inventing price "
    "history. Disclose returned warnings or empty payloads as data quality or "
    "provider limitations."
)
_HISTORY_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _HISTORY_SYMBOL_LIMIT,
        },
        "range": {
            "type": ["string", "null"],
            "enum": ["1mo", "3mo", "ytd", "1y", "max", None],
        },
        "pointLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _HISTORY_MAX_POINT_LIMIT,
        },
    },
    "required": ["symbols", "range", "pointLimit"],
    "unevaluatedProperties": False,
}

_OHLCV_LOOKUP_DESCRIPTION = (
    "Read provider-backed daily OHLCV rows for up to 5 symbols and bounded dates."
)
_OHLCV_LOOKUP_GUIDANCE = (
    "When you need daily OHLCV bars, call signaldeck_finance_market_data_ohlcv_lookup "
    "with explicit date bounds instead of inventing bars. Disclose returned warnings "
    "or empty payloads as data quality or provider limitations, and do not claim "
    "coverage beyond the rows returned by SignalDeck."
)
_OHLCV_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": _MARKET_DATA_SYMBOL_LIMIT,
        },
        "startDate": {"type": "string"},
        "endDate": {"type": "string"},
        "rowLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _OHLCV_MAX_ROW_LIMIT,
        },
    },
    "required": ["symbols", "startDate", "endDate", "rowLimit"],
    "unevaluatedProperties": False,
}

_INDICATORS_LOOKUP_DESCRIPTION = (
    "Read close-price and technical-analysis indicator rows for " "one symbol over bounded dates."
)
_INDICATORS_LOOKUP_GUIDANCE = (
    "When you need technical indicators, call signaldeck_finance_indicators_lookup with "
    "currentDate, startDate, endDate, and explicit indicators. Treat null values as warmup, "
    "insufficient history, or provider gaps, disclose warnings or empty payloads as data "
    "quality or provider limitations, and do not infer unsupported indicators."
)
_INDICATORS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "currentDate": {"type": "string"},
        "startDate": {"type": "string"},
        "endDate": {"type": "string"},
        "indicators": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "sma",
                            "ema",
                            "rsi",
                            "macd",
                            "bollinger_bands",
                            "atr",
                            "vwma",
                        ],
                    },
                    "window": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": _INDICATOR_MAX_ROW_LIMIT,
                    },
                    "fastWindow": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": _INDICATOR_MAX_ROW_LIMIT,
                    },
                    "slowWindow": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": _INDICATOR_MAX_ROW_LIMIT,
                    },
                    "signalWindow": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": _INDICATOR_MAX_ROW_LIMIT,
                    },
                    "standardDeviations": {
                        "type": ["number", "null"],
                        "minimum": 0,
                        "maximum": 10,
                    },
                },
                "required": ["type"],
                "unevaluatedProperties": False,
            },
            "minItems": 1,
            "maxItems": _INDICATOR_MAX_SELECTIONS,
        },
        "rowLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _INDICATOR_MAX_ROW_LIMIT,
        },
    },
    "required": [
        "symbol",
        "currentDate",
        "startDate",
        "endDate",
        "indicators",
        "rowLimit",
    ],
    "unevaluatedProperties": False,
}

_FUNDAMENTALS_LOOKUP_DESCRIPTION = (
    "Read provider-backed fundamentals metrics and filtered " "financial statements for one symbol."
)
_FUNDAMENTALS_LOOKUP_GUIDANCE = (
    "When you need fundamentals, call signaldeck_finance_fundamentals_lookup instead of inventing "
    "metrics or statements. Use only the returned data, disclose warnings or empty payloads "
    "as data quality or provider limitations, and do not claim unavailable coverage."
)
_FUNDAMENTALS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "metricNames": {
            "type": ["array", "null"],
            "items": {
                "type": "string",
                "enum": sorted(_FUNDAMENTAL_METRIC_NAMES),
            },
        },
        "statementTypes": {
            "type": ["array", "null"],
            "items": {
                "type": "string",
                "enum": ["income_statement", "balance_sheet", "cash_flow"],
            },
        },
        "periods": {
            "type": ["array", "null"],
            "items": {
                "type": "string",
                "enum": ["annual", "quarterly", "trailing_twelve_months"],
            },
        },
        "statementLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _FUNDAMENTALS_MAX_STATEMENT_LIMIT,
        },
    },
    "required": [
        "symbol",
        "metricNames",
        "statementTypes",
        "periods",
        "statementLimit",
    ],
    "unevaluatedProperties": False,
}

_NEWS_LOOKUP_DESCRIPTION = (
    "Read provider-backed symbol, market, or global finance news for optional symbols, "
    "query text, and bounded dates."
)
_NEWS_LOOKUP_GUIDANCE = (
    "When you need market or global finance news, call signaldeck_finance_news_lookup "
    "with scope, symbols, query, or a combination instead of inventing articles. Use "
    "signaldeck_finance_social_sentiment_lookup separately for retail/social sentiment. "
    "Disclose warnings or empty results as data quality or provider limitations, and "
    "do not present unsupported provider coverage as if it were available."
)
_NEWS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbols": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "maxItems": _MARKET_DATA_SYMBOL_LIMIT,
        },
        "query": {"type": ["string", "null"], "maxLength": 240},
        "scope": {
            "type": ["string", "null"],
            "enum": ["symbol", "market", "global", None],
        },
        "startDate": {"type": ["string", "null"]},
        "endDate": {"type": ["string", "null"]},
        "itemLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _NEWS_MAX_ITEM_LIMIT,
        },
    },
    "required": ["symbols", "query", "scope", "startDate", "endDate", "itemLimit"],
    "unevaluatedProperties": False,
}

_SOCIAL_SENTIMENT_LOOKUP_DESCRIPTION = (
    "Read provider-backed social sentiment source blocks for one " "symbol and optional sources."
)
_SOCIAL_SENTIMENT_LOOKUP_GUIDANCE = (
    "When you need retail or social sentiment, call "
    "signaldeck_finance_social_sentiment_lookup with a symbol instead of treating news "
    "as social data. Use only returned source blocks and metrics, disclose warnings or "
    "empty payloads as data quality or provider limitations, and keep this output "
    "separate from signaldeck_finance_news_lookup results."
)
_SOCIAL_SENTIMENT_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "sources": {
            "type": ["array", "null"],
            "items": {
                "type": "string",
                "enum": ["reddit", "stocktwits"],
            },
        },
        "startDate": {"type": ["string", "null"]},
        "endDate": {"type": ["string", "null"]},
        "itemLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _SOCIAL_SENTIMENT_MAX_ITEM_LIMIT,
        },
    },
    "required": ["symbol", "sources", "startDate", "endDate", "itemLimit"],
    "unevaluatedProperties": False,
}

_INSIDER_DATA_LOOKUP_DESCRIPTION = (
    "Read provider-backed insider transactions for one symbol " "and optional bounded dates."
)
_INSIDER_DATA_LOOKUP_GUIDANCE = (
    "When you need insider transactions, call signaldeck_finance_insider_data_lookup "
    "with a symbol and optional date bounds. Disclose warnings or empty payloads as "
    "data quality or provider limitations, and do not fabricate transaction coverage."
)
_INSIDER_DATA_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "startDate": {"type": ["string", "null"]},
        "endDate": {"type": ["string", "null"]},
        "transactionLimit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": _INSIDER_MAX_TRANSACTION_LIMIT,
        },
    },
    "required": ["symbol", "startDate", "endDate", "transactionLimit"],
    "unevaluatedProperties": False,
}


def parse_quote_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols"},
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbols": _parse_symbols_argument(
            raw_arguments.get("symbols"),
            function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
            maximum=_QUOTE_SYMBOL_LIMIT,
        ),
    }


def parse_history_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "range", "pointLimit"},
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbols": _parse_symbols_argument(
            raw_arguments.get("symbols"),
            function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            maximum=_HISTORY_SYMBOL_LIMIT,
        ),
        "range": _parse_history_range(raw_arguments.get("range")),
        "point_limit": _parse_optional_integer_argument(
            raw_arguments.get("pointLimit"),
            function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="pointLimit",
            minimum=1,
            maximum=_HISTORY_MAX_POINT_LIMIT,
        )
        or _HISTORY_DEFAULT_POINT_LIMIT,
    }


def parse_ohlcv_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "startDate", "endDate", "rowLimit"},
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_required_datetime_argument(
        raw_arguments.get("startDate"),
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="startDate",
    )
    end_date = _parse_required_datetime_argument(
        raw_arguments.get("endDate"),
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="endDate",
    )
    _validate_date_bounds(
        start_date,
        end_date,
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbols": _parse_symbols_argument(
            raw_arguments.get("symbols"),
            function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
            maximum=_MARKET_DATA_SYMBOL_LIMIT,
        ),
        "start_date": start_date,
        "end_date": end_date,
        "row_limit": _parse_optional_integer_argument(
            raw_arguments.get("rowLimit"),
            function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="rowLimit",
            minimum=1,
            maximum=_OHLCV_MAX_ROW_LIMIT,
        )
        or _OHLCV_DEFAULT_ROW_LIMIT,
    }


def parse_indicators_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "symbol",
            "currentDate",
            "startDate",
            "endDate",
            "indicators",
            "rowLimit",
        },
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    current_date = _parse_required_datetime_argument(
        raw_arguments.get("currentDate"),
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="currentDate",
    )
    start_date = _parse_required_datetime_argument(
        raw_arguments.get("startDate"),
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="startDate",
    )
    end_date = _parse_required_datetime_argument(
        raw_arguments.get("endDate"),
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="endDate",
    )
    _validate_date_bounds(
        start_date,
        end_date,
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    if end_date > current_date:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} endDate cannot be after currentDate."
            ),
        )
    return {
        "symbol": _parse_required_symbol_argument(
            raw_arguments.get("symbol"),
            function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="symbol",
        ),
        "current_date": current_date,
        "start_date": start_date,
        "end_date": end_date,
        "indicators": _parse_indicator_selection_argument(raw_arguments.get("indicators")),
        "row_limit": _parse_optional_integer_argument(
            raw_arguments.get("rowLimit"),
            function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="rowLimit",
            minimum=1,
            maximum=_INDICATOR_MAX_ROW_LIMIT,
        )
        or _INDICATOR_DEFAULT_ROW_LIMIT,
    }


def parse_fundamentals_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "symbol",
            "metricNames",
            "statementTypes",
            "periods",
            "statementLimit",
        },
        function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "symbol": _parse_required_symbol_argument(
            raw_arguments.get("symbol"),
            function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="symbol",
        ),
        "metric_names": _parse_optional_string_list_argument(
            raw_arguments.get("metricNames"),
            function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="metricNames",
            allowed_values=_FUNDAMENTAL_METRIC_NAMES,
        ),
        "statement_types": _parse_optional_string_list_argument(
            raw_arguments.get("statementTypes"),
            function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="statementTypes",
            allowed_values=_FINANCIAL_STATEMENT_TYPES,
        ),
        "periods": _parse_optional_string_list_argument(
            raw_arguments.get("periods"),
            function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="periods",
            allowed_values=_FINANCIAL_STATEMENT_PERIODS,
        ),
        "statement_limit": _parse_optional_integer_argument(
            raw_arguments.get("statementLimit"),
            function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="statementLimit",
            minimum=1,
            maximum=_FUNDAMENTALS_MAX_STATEMENT_LIMIT,
        )
        or _FUNDAMENTALS_DEFAULT_STATEMENT_LIMIT,
    }


def parse_news_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbols", "query", "scope", "startDate", "endDate", "itemLimit"},
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_optional_datetime_argument(
        raw_arguments.get("startDate"),
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="startDate",
    )
    end_date = _parse_optional_datetime_argument(
        raw_arguments.get("endDate"),
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="endDate",
    )
    if start_date is not None and end_date is not None:
        _validate_date_bounds(start_date, end_date, function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME)
    symbols = _parse_optional_symbols_argument(
        raw_arguments.get("symbols"),
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        maximum=_MARKET_DATA_SYMBOL_LIMIT,
    )
    query = _parse_optional_string_argument(
        raw_arguments.get("query"),
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="query",
    )
    if query is not None and len(query) > 240:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{NEWS_LOOKUP_OPENAI_FUNCTION_NAME} query must be at most 240 characters.",
        )
    scope = _parse_news_scope_argument(raw_arguments.get("scope"), symbols=symbols)
    return {
        "symbols": symbols,
        "query": query,
        "scope": scope,
        "start_date": start_date,
        "end_date": end_date,
        "item_limit": _parse_optional_integer_argument(
            raw_arguments.get("itemLimit"),
            function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="itemLimit",
            minimum=1,
            maximum=_NEWS_MAX_ITEM_LIMIT,
        )
        or _NEWS_DEFAULT_ITEM_LIMIT,
    }


def parse_social_sentiment_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbol", "sources", "startDate", "endDate", "itemLimit"},
        function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_optional_datetime_argument(
        raw_arguments.get("startDate"),
        function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="startDate",
    )
    end_date = _parse_optional_datetime_argument(
        raw_arguments.get("endDate"),
        function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="endDate",
    )
    if start_date is not None and end_date is not None:
        _validate_date_bounds(
            start_date,
            end_date,
            function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
        )
    return {
        "symbol": _parse_required_symbol_argument(
            raw_arguments.get("symbol"),
            function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="symbol",
        ),
        "sources": _parse_optional_string_list_argument(
            raw_arguments.get("sources"),
            function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="sources",
            allowed_values=_SOCIAL_SENTIMENT_SOURCES,
        )
        or tuple(sorted(_SOCIAL_SENTIMENT_SOURCES)),
        "start_date": start_date,
        "end_date": end_date,
        "item_limit": _parse_optional_integer_argument(
            raw_arguments.get("itemLimit"),
            function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="itemLimit",
            minimum=1,
            maximum=_SOCIAL_SENTIMENT_MAX_ITEM_LIMIT,
        )
        or _SOCIAL_SENTIMENT_DEFAULT_ITEM_LIMIT,
    }


def parse_insider_data_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"symbol", "startDate", "endDate", "transactionLimit"},
        function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_optional_datetime_argument(
        raw_arguments.get("startDate"),
        function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="startDate",
    )
    end_date = _parse_optional_datetime_argument(
        raw_arguments.get("endDate"),
        function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="endDate",
    )
    if start_date is not None and end_date is not None:
        _validate_date_bounds(
            start_date,
            end_date,
            function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
        )
    return {
        "symbol": _parse_required_symbol_argument(
            raw_arguments.get("symbol"),
            function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="symbol",
        ),
        "start_date": start_date,
        "end_date": end_date,
        "transaction_limit": _parse_optional_integer_argument(
            raw_arguments.get("transactionLimit"),
            function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="transactionLimit",
            minimum=1,
            maximum=_INSIDER_MAX_TRANSACTION_LIMIT,
        )
        or _INSIDER_DEFAULT_TRANSACTION_LIMIT,
    }


def execute_quote_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    quotes: list[MarketQuoteRead] = []
    warnings: list[RuntimeToolWarning] = []

    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        for symbol in cast(list[str], arguments["symbols"]):
            quote, raw_warnings = service.get_quote_snapshot(
                symbol=symbol,
            )
            if quote is not None:
                quotes.append(quote)
            warnings.extend(
                _warning_models(raw_warnings, symbol=symbol, default_code="quote_unavailable")
            )

    return cast(
        dict[str, object],
        RuntimeQuoteLookupResult(quotes=quotes, warnings=warnings).model_dump(
            mode="json",
            by_alias=True,
        ),
    )


def execute_history_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    range_value = cast(str, arguments["range"])
    point_limit = cast(int, arguments["point_limit"])
    series: list[MarketHistorySeriesRead] = []
    warnings: list[RuntimeToolWarning] = []

    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        for symbol in cast(list[str], arguments["symbols"]):
            try:
                history = service.get_history_snapshot(
                    symbol=symbol,
                    range_value=range_value,
                )
            except QuoteProviderError as exc:
                warnings.append(_warning_model(str(exc), symbol=symbol, code="history_unavailable"))
                continue
            series.extend(_trim_history_series(history.series, point_limit=point_limit))
            warnings.extend(
                _warning_models(history.warnings, symbol=symbol, default_code="history_unavailable")
            )

    bounds = _history_bounds(series)
    return cast(
        dict[str, object],
        RuntimeHistoryLookupResult(
            range=range_value,
            interval=MarketDataService.history_interval_by_range[range_value],
            start_date=bounds[0],
            end_date=bounds[1],
            series=series,
            warnings=warnings,
        ).model_dump(mode="json", by_alias=True),
    )


def execute_ohlcv_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        result = service.get_ohlcv_snapshot(
            cast(list[str], arguments["symbols"]),
            start_date=cast(datetime, arguments["start_date"]),
            end_date=cast(datetime, arguments["end_date"]),
            row_limit=cast(int, arguments["row_limit"]),
        )
    runtime_result = RuntimeOhlcvLookupResult.model_validate(result, from_attributes=True)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def execute_indicators_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        result = service.get_indicator_snapshot(
            cast(str, arguments["symbol"]),
            current_date=cast(datetime, arguments["current_date"]),
            start_date=cast(datetime, arguments["start_date"]),
            end_date=cast(datetime, arguments["end_date"]),
            indicators=cast(tuple[MarketIndicatorSelection, ...], arguments["indicators"]),
            row_limit=cast(int, arguments["row_limit"]),
        )
    runtime_result = RuntimeIndicatorLookupResult.model_validate(result, from_attributes=True)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def execute_fundamentals_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    with context.session_factory() as session:
        result = MarketDataService(
            session=session,
            quote_provider=quote_provider,
        ).get_fundamentals_snapshot(cast(str, arguments["symbol"]))
    filtered_metrics = [
        metric
        for metric in result.metrics
        if _metric_matches_filters(
            name=metric.name,
            metric_names=cast(tuple[str, ...] | None, arguments["metric_names"]),
        )
    ]
    filtered_statements = [
        statement
        for statement in result.statements
        if _statement_matches_filters(
            statement_type=statement.statement_type,
            period=statement.period,
            statement_types=cast(tuple[str, ...] | None, arguments["statement_types"]),
            periods=cast(tuple[str, ...] | None, arguments["periods"]),
        )
    ][: cast(int, arguments["statement_limit"])]
    runtime_result = RuntimeFundamentalsLookupResult.model_validate(
        result.model_copy(update={"metrics": filtered_metrics, "statements": filtered_statements}),
        from_attributes=True,
    )
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def execute_news_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    news_providers = _runtime_news_providers(context)
    with context.session_factory() as session:
        service = MarketDataService(session=session, quote_provider=quote_provider)
        result = service.get_news_snapshot(
            symbols=cast(list[str], arguments["symbols"]),
            query=cast(str | None, arguments["query"]),
            scope=cast(NewsScope, arguments["scope"]),
            start_date=cast(datetime | None, arguments["start_date"]),
            end_date=cast(datetime | None, arguments["end_date"]),
            item_limit=cast(int, arguments["item_limit"]),
            providers=news_providers,
        )
    runtime_result = RuntimeNewsLookupResult.model_validate(result, from_attributes=True)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def _runtime_news_providers(context: RuntimeToolContext) -> tuple[NewsProvider, ...]:
    configured_providers = context.news_providers
    if configured_providers:
        return configured_providers
    return ()


def execute_social_sentiment_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    from finance_plugin.providers.social_sentiment_service import SocialSentimentService

    service = SocialSentimentService(source_adapters=context.social_sentiment_adapters)
    result = service.get_social_sentiment_snapshot(
        cast(str, arguments["symbol"]),
        sources=cast(tuple[str, ...], arguments["sources"]),
        start_date=cast(datetime | None, arguments["start_date"]),
        end_date=cast(datetime | None, arguments["end_date"]),
        item_limit=cast(int, arguments["item_limit"]),
    )
    runtime_result = RuntimeSocialSentimentLookupResult.model_validate(result, from_attributes=True)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def execute_insider_data_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    quote_provider = _require_quote_provider(
        context,
        function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    with context.session_factory() as session:
        result = MarketDataService(
            session=session,
            quote_provider=quote_provider,
        ).get_insider_transactions_snapshot(
            cast(str, arguments["symbol"]),
            start_date=cast(datetime | None, arguments["start_date"]),
            end_date=cast(datetime | None, arguments["end_date"]),
            transaction_limit=cast(int, arguments["transaction_limit"]),
        )
    runtime_result = RuntimeInsiderDataLookupResult.model_validate(result, from_attributes=True)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"OpenAI response requested {function_name} with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} arguments must be a JSON object.",
        )
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(
    raw_arguments: dict[str, object],
    *,
    allowed_keys: set[str],
    function_name: str,
) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{function_name} arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )


def _parse_symbols_argument(value: object, *, function_name: str, maximum: int) -> list[str]:
    if value is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols is required.",
        )
    return _parse_symbol_list(
        value,
        function_name=function_name,
        maximum=maximum,
        require_non_empty=True,
    )


def _parse_optional_symbols_argument(
    value: object,
    *,
    function_name: str,
    maximum: int,
) -> list[str]:
    if value is None:
        return []
    return _parse_symbol_list(
        value,
        function_name=function_name,
        maximum=maximum,
        require_non_empty=False,
    )


def _parse_symbol_list(
    value: object,
    *,
    function_name: str,
    maximum: int,
    require_non_empty: bool,
) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must be an array of strings.",
        )
    raw_symbols = cast(list[object], value)
    symbols: list[str] = []
    seen_symbols: set[str] = set()
    for raw_symbol in raw_symbols:
        if not isinstance(raw_symbol, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} symbols must be an array of strings.",
            )
        symbol = normalize_symbol(raw_symbol)
        if not symbol:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} symbols must not contain empty values.",
            )
        if symbol in seen_symbols:
            continue
        symbols.append(symbol)
        seen_symbols.add(symbol)
    if require_non_empty and not symbols:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must contain at least one symbol.",
        )
    if len(symbols) > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} symbols must contain at most {maximum} symbols.",
        )
    return symbols


def _parse_required_symbol_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
) -> str:
    symbol = _parse_optional_string_argument(
        value,
        function_name=function_name,
        field_name=field_name,
    )
    if symbol is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} is required.",
        )
    normalized = normalize_symbol(symbol)
    if not normalized:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must not be empty.",
        )
    return normalized


def _parse_optional_string_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be a string.",
        )
    normalized = value.strip()
    return normalized or None


def _parse_news_scope_argument(
    value: object,
    *,
    symbols: list[str],
) -> str:
    if value is None:
        return "symbol" if symbols else "market"
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{NEWS_LOOKUP_OPENAI_FUNCTION_NAME} scope must be a string.",
        )
    normalized = value.strip().lower()
    if normalized not in _NEWS_SCOPES:
        allowed_values_text = ", ".join(sorted(_NEWS_SCOPES))
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{NEWS_LOOKUP_OPENAI_FUNCTION_NAME} scope must use: " f"{allowed_values_text}."
            ),
        )
    if normalized == "symbol" and not symbols:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{NEWS_LOOKUP_OPENAI_FUNCTION_NAME} scope symbol requires symbols.",
        )
    return normalized


def _parse_history_range(value: object) -> str:
    if value is None:
        return "3mo"
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME} range must be a string.",
        )
    normalized = value.strip().lower()
    if normalized not in _HISTORY_RANGES:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME} "
                "range must be one of 1mo, 3mo, ytd, 1y, or max."
            ),
        )
    return normalized


def _parse_optional_integer_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be an integer.",
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be at least {minimum}.",
        )
    if value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be at most {maximum}.",
        )
    return int(value)


def _parse_indicator_selection_argument(
    value: object,
) -> tuple[MarketIndicatorSelection, ...]:
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicators must be an array.",
        )
    raw_selections = cast(list[object], value)
    if len(raw_selections) > _INDICATOR_MAX_SELECTIONS:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicators must contain "
                f"at most {_INDICATOR_MAX_SELECTIONS} selections."
            ),
        )
    selections: list[MarketIndicatorSelection] = []
    seen_keys: set[tuple[object, ...]] = set()
    for raw_selection in raw_selections:
        if not isinstance(raw_selection, dict):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicators must be "
                    "an array of objects."
                ),
            )
        selection = _parse_indicator_selection(cast(dict[str, object], raw_selection))
        key = _indicator_selection_key(selection)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selections.append(selection)
    if not selections:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicators must not be empty.",
        )
    return tuple(selections)


def _parse_indicator_selection(raw_selection: dict[str, object]) -> MarketIndicatorSelection:
    _reject_unexpected_keys(
        raw_selection,
        allowed_keys={
            "type",
            "window",
            "fastWindow",
            "slowWindow",
            "signalWindow",
            "standardDeviations",
        },
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    indicator_type = _parse_indicator_type(raw_selection.get("type"))
    if indicator_type in {"sma", "ema", "rsi", "atr", "vwma"}:
        return MarketIndicatorSelection(
            indicator=indicator_type,
            window=_parse_required_indicator_integer(raw_selection.get("window"), "window"),
        )
    if indicator_type == "macd":
        fast_window = _parse_required_indicator_integer(
            raw_selection.get("fastWindow"), "fastWindow"
        )
        slow_window = _parse_required_indicator_integer(
            raw_selection.get("slowWindow"), "slowWindow"
        )
        signal_window = _parse_required_indicator_integer(
            raw_selection.get("signalWindow"),
            "signalWindow",
        )
        if fast_window >= slow_window:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} MACD fastWindow must be "
                    "less than slowWindow."
                ),
            )
        return MarketIndicatorSelection(
            indicator="macd",
            fast_window=fast_window,
            slow_window=slow_window,
            signal_window=signal_window,
        )
    if indicator_type == "bollinger_bands":
        return MarketIndicatorSelection(
            indicator="bollinger_bands",
            window=_parse_required_indicator_integer(raw_selection.get("window"), "window"),
            standard_deviations=_parse_standard_deviations(raw_selection.get("standardDeviations")),
        )
    raise RuntimeToolError(
        code="agent_tool_call_invalid",
        message=f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicator type is unsupported.",
    )


def _parse_indicator_type(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicator type is required.",
        )
    normalized = value.strip().lower()
    if normalized not in _INDICATOR_TYPES:
        allowed_values_text = ", ".join(sorted(_INDICATOR_TYPES))
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} indicator type must use: "
                f"{allowed_values_text}."
            ),
        )
    return normalized


def _parse_required_indicator_integer(value: object, field_name: str) -> int:
    parsed_value = _parse_optional_integer_argument(
        value,
        function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name=field_name,
        minimum=1,
        maximum=_INDICATOR_MAX_ROW_LIMIT,
    )
    if parsed_value is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} is required.",
        )
    return parsed_value


def _parse_standard_deviations(value: object) -> Decimal:
    if value is None:
        return Decimal("2")
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} standardDeviations must be "
                "a number or numeric string."
            ),
        )
    try:
        parsed_value = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} standardDeviations must be "
                "a finite positive number."
            ),
        ) from exc
    if not parsed_value.is_finite() or parsed_value <= 0:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} standardDeviations must be "
                "a finite positive number."
            ),
        )
    if parsed_value > Decimal("10"):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME} standardDeviations "
                "must be at most 10."
            ),
        )
    return parsed_value


def _indicator_selection_key(selection: MarketIndicatorSelection) -> tuple[object, ...]:
    if selection.indicator in {"sma", "ema", "rsi", "atr", "vwma"}:
        return (selection.indicator, selection.window)
    if selection.indicator == "macd":
        return (
            selection.indicator,
            selection.fast_window,
            selection.slow_window,
            selection.signal_window,
        )
    return (selection.indicator, selection.window, selection.standard_deviations)


def _parse_optional_string_list_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
    allowed_values: set[str],
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be an array of strings.",
        )
    values: list[str] = []
    seen_values: set[str] = set()
    for raw_value in cast(list[object], value):
        if not isinstance(raw_value, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} {field_name} must be an array of strings.",
            )
        normalized = raw_value.strip().lower()
        if not normalized:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} {field_name} must not contain empty values.",
            )
        if normalized not in allowed_values:
            allowed_values_text = ", ".join(sorted(allowed_values))
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} {field_name} must use: {allowed_values_text}.",
            )
        if normalized in seen_values:
            continue
        values.append(normalized)
        seen_values.add(normalized)
    if not values:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must contain at least one value.",
        )
    return tuple(values)


def _parse_required_datetime_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
) -> datetime:
    parsed = _parse_optional_datetime_argument(
        value,
        function_name=function_name,
        field_name=field_name,
    )
    if parsed is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} is required.",
        )
    return parsed


def _parse_optional_datetime_argument(
    value: object,
    *,
    function_name: str,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be a string date or datetime.",
        )
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} {field_name} must be a valid ISO date or datetime.",
        )
    return _parse_iso_datetime(raw_value, function_name=function_name, field_name=field_name)


def _parse_iso_datetime(value: str, *, function_name: str, field_name: str) -> datetime:
    iso_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return to_utc(datetime.fromisoformat(iso_value))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=f"{function_name} {field_name} must be a valid ISO date or datetime.",
            ) from exc
        return datetime.combine(parsed_date, time.min, tzinfo=UTC)


def _validate_date_bounds(start_date: datetime, end_date: datetime, *, function_name: str) -> None:
    if start_date > end_date:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} startDate must be before or equal to endDate.",
        )


def _statement_matches_filters(
    *,
    statement_type: str,
    period: str,
    statement_types: tuple[str, ...] | None,
    periods: tuple[str, ...] | None,
) -> bool:
    if statement_types is not None and statement_type not in statement_types:
        return False
    if periods is not None and period not in periods:
        return False
    return True


def _metric_matches_filters(
    *,
    name: str,
    metric_names: tuple[str, ...] | None,
) -> bool:
    return metric_names is None or name in metric_names


def _require_quote_provider(context: RuntimeToolContext, *, function_name: str) -> QuoteProvider:
    quote_provider = context.quote_provider
    if quote_provider is None:
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=f"{function_name} requires an injected quote provider.",
        )
    return cast(QuoteProvider, quote_provider)


def _trim_history_series(
    series: list[MarketHistorySeriesRead],
    *,
    point_limit: int,
) -> list[MarketHistorySeriesRead]:
    trimmed: list[MarketHistorySeriesRead] = []
    for item in series:
        points = item.points[-point_limit:]
        trimmed.append(
            MarketHistorySeriesRead(
                symbol=item.symbol,
                currency=item.currency,
                provider=item.provider,
                points=points,
            )
        )
    return trimmed


def _history_bounds(
    series: list[MarketHistorySeriesRead],
) -> tuple[datetime | None, datetime | None]:
    point_times = [point.at for item in series for point in item.points]
    if not point_times:
        return None, None
    return min(point_times), max(point_times)


def _warning_models(
    messages: list[str],
    *,
    symbol: str,
    default_code: str,
) -> list[RuntimeToolWarning]:
    return [_warning_model(message, symbol=symbol, code=default_code) for message in messages]


def _warning_model(message: str, *, symbol: str, code: str) -> RuntimeToolWarning:
    normalized_message = " ".join(message.split()).strip()
    return RuntimeToolWarning(
        code=code,
        message=normalized_message or f"Market data unavailable for {symbol}.",
        details={"symbol": symbol},
    )


MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Data Quote Lookup",
    description=_QUOTE_LOOKUP_DESCRIPTION,
    parameters_schema=_QUOTE_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_QUOTE_LOOKUP_GUIDANCE,
    sort_order=30,
    denied_code=MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_DATA_QUOTE_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_quote_lookup_arguments,
    executor=execute_quote_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Data History Lookup",
    description=_HISTORY_LOOKUP_DESCRIPTION,
    parameters_schema=_HISTORY_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_HISTORY_LOOKUP_GUIDANCE,
    sort_order=40,
    denied_code=MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_DATA_HISTORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_history_lookup_arguments,
    executor=execute_history_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_DATA_OHLCV_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Data OHLCV Lookup",
    description=_OHLCV_LOOKUP_DESCRIPTION,
    parameters_schema=_OHLCV_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_OHLCV_LOOKUP_GUIDANCE,
    sort_order=50,
    denied_code=MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_ohlcv_lookup_arguments,
    executor=execute_ohlcv_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

INDICATORS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=INDICATORS_LOOKUP_TOOL_KEY,
    openai_function_name=INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Indicators Lookup",
    description=_INDICATORS_LOOKUP_DESCRIPTION,
    parameters_schema=_INDICATORS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_INDICATORS_LOOKUP_GUIDANCE,
    sort_order=60,
    denied_code=INDICATORS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=INDICATORS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_indicators_lookup_arguments,
    executor=execute_indicators_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

FUNDAMENTALS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=FUNDAMENTALS_LOOKUP_TOOL_KEY,
    openai_function_name=FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Fundamentals Lookup",
    description=_FUNDAMENTALS_LOOKUP_DESCRIPTION,
    parameters_schema=_FUNDAMENTALS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_FUNDAMENTALS_LOOKUP_GUIDANCE,
    sort_order=70,
    denied_code=FUNDAMENTALS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=FUNDAMENTALS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_fundamentals_lookup_arguments,
    executor=execute_fundamentals_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

NEWS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=NEWS_LOOKUP_TOOL_KEY,
    openai_function_name=NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="News Lookup",
    description=_NEWS_LOOKUP_DESCRIPTION,
    parameters_schema=_NEWS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_NEWS_LOOKUP_GUIDANCE,
    sort_order=80,
    denied_code=NEWS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=NEWS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_news_lookup_arguments,
    executor=execute_news_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=SOCIAL_SENTIMENT_LOOKUP_TOOL_KEY,
    openai_function_name=SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Social Sentiment Lookup",
    description=_SOCIAL_SENTIMENT_LOOKUP_DESCRIPTION,
    parameters_schema=_SOCIAL_SENTIMENT_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_SOCIAL_SENTIMENT_LOOKUP_GUIDANCE,
    sort_order=85,
    denied_code=SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_social_sentiment_lookup_arguments,
    executor=execute_social_sentiment_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

INSIDER_DATA_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=INSIDER_DATA_LOOKUP_TOOL_KEY,
    openai_function_name=INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Insider Data Lookup",
    description=_INSIDER_DATA_LOOKUP_DESCRIPTION,
    parameters_schema=_INSIDER_DATA_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_INSIDER_DATA_LOOKUP_GUIDANCE,
    sort_order=90,
    denied_code=INSIDER_DATA_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=INSIDER_DATA_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_insider_data_lookup_arguments,
    executor=execute_insider_data_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

__all__ = [
    "FUNDAMENTALS_LOOKUP_ACCESS_DENIED_CODE",
    "FUNDAMENTALS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME",
    "FUNDAMENTALS_LOOKUP_TOOL_SPEC",
    "INDICATORS_LOOKUP_ACCESS_DENIED_CODE",
    "INDICATORS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME",
    "INDICATORS_LOOKUP_TOOL_SPEC",
    "INSIDER_DATA_LOOKUP_ACCESS_DENIED_CODE",
    "INSIDER_DATA_LOOKUP_ACCESS_DENIED_MESSAGE",
    "INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME",
    "INSIDER_DATA_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_CODE",
    "MARKET_DATA_OHLCV_LOOKUP_ACCESS_DENIED_MESSAGE",
    "MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC",
    "NEWS_LOOKUP_ACCESS_DENIED_CODE",
    "NEWS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "NEWS_LOOKUP_OPENAI_FUNCTION_NAME",
    "NEWS_LOOKUP_TOOL_SPEC",
    "SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE",
    "SOCIAL_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE",
    "SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME",
    "SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC",
    "execute_fundamentals_lookup",
    "execute_history_lookup",
    "execute_indicators_lookup",
    "execute_insider_data_lookup",
    "execute_news_lookup",
    "execute_ohlcv_lookup",
    "execute_quote_lookup",
    "execute_social_sentiment_lookup",
    "parse_fundamentals_lookup_arguments",
    "parse_history_lookup_arguments",
    "parse_indicators_lookup_arguments",
    "parse_insider_data_lookup_arguments",
    "parse_news_lookup_arguments",
    "parse_ohlcv_lookup_arguments",
    "parse_quote_lookup_arguments",
    "parse_social_sentiment_lookup_arguments",
]
