from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Protocol, cast

import httpx
from oracle_plugin.config import DigitalOracleSettings, MarketSentimentIndicator
from oracle_plugin.contracts import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from oracle_plugin.factory import (
    create_digital_oracle_phase1_provider_bundle,
    create_market_sentiment_provider,
)
from oracle_plugin.mappers import map_market_sentiment_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_types import MARKET_SENTIMENT_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import (
    DigitalOracleMarketSentimentProvider,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentProviderResult,
    DigitalOracleMarketSentimentQuery,
    DigitalOracleProviderError,
)

MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_digital_oracle_market_sentiment_lookup"
MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY
]

_FEAR_GREED_GRAPH_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_USER_AGENT = "signaldeck-backend/0.1"
_HISTORY_FIELD_KEYS = {
    "previousClose": ("previous_close", "previousClose", "previousCloseScore"),
    "weekAgo": ("previous_1_week", "week_ago", "weekAgo", "weekAgoScore"),
    "monthAgo": ("previous_1_month", "month_ago", "monthAgo", "monthAgoScore"),
    "yearAgo": ("previous_1_year", "year_ago", "yearAgo", "yearAgoScore"),
}

_MARKET_SENTIMENT_LOOKUP_DESCRIPTION = (
    "Read the normalized market-level Fear & Greed composite with history snapshots."
)
_MARKET_SENTIMENT_LOOKUP_GUIDANCE = (
    "When you need broad market sentiment, call signaldeck_digital_oracle_market_sentiment_lookup "
    "with indicator=fear_greed. Treat it as a market-level composite only, keep it "
    "separate from issuer-specific social sentiment or news tone, disclose warnings "
    "for unavailable or sparse history, and never invent missing readings."
)
_MARKET_SENTIMENT_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "indicator": {"type": "string", "enum": ["fear_greed"]},
        "asOfDate": {"type": "string"},
    },
    "required": ["indicator"],
    "unevaluatedProperties": False,
}


class _FearGreedJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        source_url: str,
    ) -> object: ...


class _HttpxFearGreedJsonClient:
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        source_url: str,
    ) -> object:
        headers = {
            "Accept": "application/json",
            "Referer": source_url,
            "User-Agent": _USER_AGENT,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=headers)
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                "Fear & Greed provider timed out while fetching market sentiment",
                code="provider_timeout",
                details={"provider": "fear_greed"},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                "Fear & Greed provider is unavailable for market sentiment",
                code="provider_unavailable",
                details={"provider": "fear_greed"},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                "Fear & Greed provider returned malformed market sentiment data",
                details={"provider": "fear_greed"},
            ) from exc


class FearGreedMarketSentimentProvider:
    provider_name: str = "fear_greed"

    def __init__(self, http_client: _FearGreedJsonClient | None = None) -> None:
        self._http_client: _FearGreedJsonClient = http_client or _HttpxFearGreedJsonClient()

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentProviderQuery,
    ) -> DigitalOracleMarketSentimentProviderResult:
        payload = self._http_client.get_json(
            _FEAR_GREED_GRAPH_URL,
            timeout=query.timeout_seconds,
            source_url=query.source_url,
        )
        return _map_fear_greed_payload(
            payload,
            provider=self.provider_name,
            query=query,
        )


def create_market_sentiment_provider_adapter() -> DigitalOracleMarketSentimentProvider:
    return FearGreedMarketSentimentProvider()


def create_market_sentiment_service(
    *,
    settings: DigitalOracleSettings | None = None,
    market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = None,
) -> DigitalOraclePhase1Service:
    provider_bundle = replace(
        create_digital_oracle_phase1_provider_bundle(settings),
        market_sentiment=create_market_sentiment_provider(settings),
    )
    return DigitalOraclePhase1Service(
        provider_bundle=provider_bundle,
        market_sentiment_provider=(
            market_sentiment_provider or create_market_sentiment_provider_adapter()
        ),
    )


def parse_market_sentiment_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"indicator", "asOfDate"},
        function_name=MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    return {
        "indicator": _parse_required_indicator_argument(raw_arguments.get("indicator")),
        "as_of_date": _parse_optional_date_argument(
            raw_arguments.get("asOfDate"),
            "asOfDate",
        ),
    }


def execute_market_sentiment_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    service = create_market_sentiment_service()
    result = service.lookup_market_sentiment(
        DigitalOracleMarketSentimentQuery(
            indicator=cast(MarketSentimentIndicator, arguments["indicator"]),
            as_of_date=cast(date | None, arguments["as_of_date"]),
        )
    )
    runtime_result = map_market_sentiment_result(result)
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


def _parse_required_indicator_argument(value: object) -> MarketSentimentIndicator:
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME} indicator is required.",
        )
    normalized = value.strip().lower()
    if normalized != "fear_greed":
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME} indicator must use: fear_greed."
            ),
        )
    return "fear_greed"


def _parse_optional_date_argument(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME} "
                f"{field_name} must be a string date."
            ),
        )
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME} "
                f"{field_name} must be a valid ISO date."
            ),
        )
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME} "
                f"{field_name} must be a valid ISO date."
            ),
        ) from exc


def _map_fear_greed_payload(
    payload: object,
    *,
    provider: str,
    query: DigitalOracleMarketSentimentProviderQuery,
) -> DigitalOracleMarketSentimentProviderResult:
    raw_payload = _mapping_payload(payload)
    snapshot = _fear_greed_snapshot(raw_payload)
    score = _score(_first_mapping_value((snapshot,), ("score", "value")))
    label = _label(_first_mapping_value((snapshot,), ("rating", "label", "valueText")), score)
    as_of_date = _snapshot_date(
        _first_mapping_value((snapshot,), ("timestamp", "asOf", "asOfDate"))
    )
    history = _history_scores(raw_payload, snapshot)
    warnings: list[RuntimeToolWarning] = []
    missing_history_fields = tuple(
        field_name for field_name, value in history.items() if value is None
    )
    if missing_history_fields:
        warnings.append(_sparse_history_warning(provider, missing_history_fields))
    return DigitalOracleMarketSentimentProviderResult(
        provider=provider,
        score=score,
        label=label,
        as_of_date=as_of_date or query.as_of_date,
        previous_close=history["previousClose"],
        week_ago=history["weekAgo"],
        month_ago=history["monthAgo"],
        year_ago=history["yearAgo"],
        source_url=query.source_url,
        warnings=tuple(warnings),
    )


def _mapping_payload(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError(
            "Fear & Greed provider returned malformed market sentiment data",
            details={"provider": "fear_greed"},
        )
    return cast(Mapping[str, object], payload)


def _fear_greed_snapshot(payload: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("fear_and_greed", "fearGreed", "fear_greed"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    if any(key in payload for key in ("score", "value", "rating", "valueText")):
        return payload
    raise DigitalOracleProviderError(
        "Fear & Greed provider returned malformed market sentiment data",
        details={"provider": "fear_greed"},
    )


def _history_scores(
    payload: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> dict[str, int | None]:
    return {
        field_name: _score(_first_mapping_value((snapshot, payload), keys))
        for field_name, keys in _HISTORY_FIELD_KEYS.items()
    }


def _first_mapping_value(
    mappings: tuple[Mapping[str, object], ...],
    keys: tuple[str, ...],
) -> object | None:
    for mapping in mappings:
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return value
    return None


def _score(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    rounded = int(round(parsed))
    if rounded < 0 or rounded > 100:
        return None
    return rounded


def _label(value: object, score: int | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return _normalize_label(value)
    if score is None:
        return None
    if score < 25:
        return "extreme_fear"
    if score < 45:
        return "fear"
    if score <= 55:
        return "neutral"
    if score <= 74:
        return "greed"
    return "extreme_greed"


def _normalize_label(value: str) -> str:
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    if normalized in {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}:
        return normalized
    return normalized


def _snapshot_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        resolved = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return resolved.astimezone(UTC).date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _epoch_date(float(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return _epoch_date(float(text))
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        iso_value = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    resolved = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return resolved.astimezone(UTC).date()


def _epoch_date(value: float) -> date | None:
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).date()
    except (OverflowError, OSError, ValueError):
        return None


def _sparse_history_warning(provider: str, missing_fields: tuple[str, ...]) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="market_sentiment_sparse_history",
        message="Fear & Greed history is incomplete for the requested market sentiment snapshot.",
        details={
            "operation": "market_sentiment",
            "provider": provider,
            "missingFields": ",".join(missing_fields),
        },
    )


def _http_status_provider_error(exc: httpx.HTTPStatusError) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            "Fear & Greed provider rate limited market sentiment lookup",
            code="provider_rate_limited",
            details={"provider": "fear_greed", "status": str(status_code)},
        )
    if status_code >= 500:
        return DigitalOracleProviderError(
            "Fear & Greed provider outage while fetching market sentiment",
            code="provider_unavailable",
            details={"provider": "fear_greed", "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        "Fear & Greed provider failed while fetching market sentiment",
        details={"provider": "fear_greed", "status": str(status_code)},
    )


MARKET_SENTIMENT_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    openai_function_name=MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Market Sentiment Lookup",
    description=_MARKET_SENTIMENT_LOOKUP_DESCRIPTION,
    parameters_schema=_MARKET_SENTIMENT_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_MARKET_SENTIMENT_LOOKUP_GUIDANCE,
    sort_order=88,
    denied_code=MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_market_sentiment_lookup_arguments,
    executor=execute_market_sentiment_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "FearGreedMarketSentimentProvider",
    "MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_CODE",
    "MARKET_SENTIMENT_LOOKUP_ACCESS_DENIED_MESSAGE",
    "MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_SENTIMENT_LOOKUP_TOOL_SPEC",
    "create_market_sentiment_provider_adapter",
    "create_market_sentiment_service",
    "execute_market_sentiment_lookup",
    "parse_market_sentiment_lookup_arguments",
]
