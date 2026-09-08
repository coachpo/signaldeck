from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

import httpx
from oracle_plugin.config import PREDICTION_MARKET_VENUES, PredictionMarketVenue
from oracle_plugin.contracts import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from oracle_plugin.mappers import map_prediction_markets_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_types import PREDICTION_MARKETS_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import (
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketOrderBook,
    DigitalOraclePredictionMarketOrderBookLevel,
    DigitalOraclePredictionMarketProvider,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOraclePredictionMarketsQuery,
    DigitalOracleProviderError,
)
from oracle_plugin.warnings import runtime_warning

PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME = (
    "signaldeck_digital_oracle_prediction_markets_lookup"
)
PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY
]

_PREDICTION_MARKETS_MAX_ITEM_LIMIT = 20
_PREDICTION_MARKETS_MAX_DEPTH_LIMIT = 10
_PREDICTION_MARKET_VENUES = set(PREDICTION_MARKET_VENUES)
_POLYMARKET_EVENTS_URL = "https://gamma-api.polymarket.com/events"
_POLYMARKET_ORDER_BOOK_URL = "https://clob.polymarket.com/book"
_KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
_USER_AGENT = "signaldeck-backend/0.1"
_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")

_PREDICTION_MARKETS_LOOKUP_DESCRIPTION = (
    "Read normalized prediction-market events and contracts across supported venues."
)
_PREDICTION_MARKETS_LOOKUP_GUIDANCE = (
    "When you need prediction-market signals, call "
    "signaldeck_digital_oracle_prediction_markets_lookup with a plain-language query "
    "and optional venue filters. Use only returned event "
    "and contract probabilities/prices, disclose all warnings as coverage limitations, "
    "and never invent probabilities for unavailable markets."
)
_PREDICTION_MARKETS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "venues": {
            "type": "array",
            "items": {"type": "string", "enum": ["polymarket", "kalshi"]},
            "minItems": 1,
            "maxItems": len(PREDICTION_MARKET_VENUES),
        },
        "itemLimit": {
            "type": "integer",
            "minimum": 1,
            "maximum": _PREDICTION_MARKETS_MAX_ITEM_LIMIT,
        },
        "includeResolved": {"type": "boolean"},
        "includeOrderBook": {"type": "boolean"},
        "depthLimit": {
            "type": "integer",
            "minimum": 1,
            "maximum": _PREDICTION_MARKETS_MAX_DEPTH_LIMIT,
        },
    },
    "required": ["query"],
    "unevaluatedProperties": False,
}


class _PredictionMarketsJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: PredictionMarketVenue,
    ) -> object: ...


class _HttpxPredictionMarketsJsonClient:
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: PredictionMarketVenue,
    ) -> object:
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    url,
                    params=_compact_params(params),
                    headers=headers,
                )
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                f"{provider} timed out while fetching prediction markets",
                code="provider_timeout",
                details={"provider": provider},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc, provider=provider) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                f"{provider} is unavailable for prediction markets",
                code="provider_unavailable",
                details={"provider": provider},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                f"{provider} returned malformed prediction-market data",
                details={"provider": provider},
            ) from exc


class PolymarketPredictionMarketsProvider:
    venue: PredictionMarketVenue = "polymarket"

    def __init__(self, http_client: _PredictionMarketsJsonClient | None = None) -> None:
        self._http_client: _PredictionMarketsJsonClient = (
            http_client or _HttpxPredictionMarketsJsonClient()
        )

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult:
        payload = self._http_client.get_json(
            _POLYMARKET_EVENTS_URL,
            params={
                "limit": query.item_limit,
                "active": None if query.include_resolved else True,
                "closed": None if query.include_resolved else False,
                "order": "volume24hr",
                "ascending": False,
                "tag_slug": _slug_search_term(query.query),
            },
            timeout=query.timeout_seconds,
            provider=self.venue,
        )
        raw_events = _object_list_payload(payload, provider=self.venue)
        warnings: list[RuntimeToolWarning] = []
        events: list[DigitalOraclePredictionMarketEvent] = []
        for item in raw_events:
            if not isinstance(item, Mapping):
                warnings.append(_malformed_warning(self.venue, "event row"))
                continue
            event = _map_polymarket_event(
                cast(Mapping[str, object], item),
                query=query,
                http_client=self._http_client,
                warnings=warnings,
            )
            if event is not None:
                events.append(event)
        return DigitalOraclePredictionMarketsProviderResult(
            provider=self.venue,
            events=tuple(_rank_prediction_events(events)[: query.item_limit]),
            warnings=tuple(warnings),
        )


class KalshiPredictionMarketsProvider:
    venue: PredictionMarketVenue = "kalshi"

    def __init__(self, http_client: _PredictionMarketsJsonClient | None = None) -> None:
        self._http_client: _PredictionMarketsJsonClient = (
            http_client or _HttpxPredictionMarketsJsonClient()
        )

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult:
        payload = self._http_client.get_json(
            _KALSHI_MARKETS_URL,
            params={
                "limit": query.item_limit,
                "status": None if query.include_resolved else "open",
                "mve_filter": "exclude",
            },
            timeout=query.timeout_seconds,
            provider=self.venue,
        )
        raw_payload = _object_payload(payload, provider=self.venue)
        raw_markets = _object_list(raw_payload.get("markets"))
        warnings: list[RuntimeToolWarning] = []
        events: list[DigitalOraclePredictionMarketEvent] = []
        for item in raw_markets:
            if not isinstance(item, Mapping):
                warnings.append(_malformed_warning(self.venue, "market row"))
                continue
            event = _map_kalshi_market(
                cast(Mapping[str, object], item),
                query=query,
                http_client=self._http_client,
                warnings=warnings,
            )
            if event is not None:
                events.append(event)
        return DigitalOraclePredictionMarketsProviderResult(
            provider=self.venue,
            events=tuple(_rank_prediction_events(events)[: query.item_limit]),
            warnings=tuple(warnings),
        )


def create_prediction_market_providers() -> tuple[DigitalOraclePredictionMarketProvider, ...]:
    return (
        PolymarketPredictionMarketsProvider(),
        KalshiPredictionMarketsProvider(),
    )


def parse_prediction_markets_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "query",
            "venues",
            "itemLimit",
            "includeResolved",
            "includeOrderBook",
            "depthLimit",
        },
        function_name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    include_order_book = _parse_optional_boolean_argument(
        raw_arguments.get("includeOrderBook"),
        field_name="includeOrderBook",
    )
    depth_limit = _parse_optional_integer_argument(
        raw_arguments.get("depthLimit"),
        function_name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
        field_name="depthLimit",
        minimum=1,
        maximum=_PREDICTION_MARKETS_MAX_DEPTH_LIMIT,
    )
    if not include_order_book:
        depth_limit = None
    return {
        "query": _parse_required_query_argument(raw_arguments.get("query")),
        "venues": _parse_venues_argument(raw_arguments.get("venues")),
        "item_limit": _parse_optional_integer_argument(
            raw_arguments.get("itemLimit"),
            function_name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
            field_name="itemLimit",
            minimum=1,
            maximum=_PREDICTION_MARKETS_MAX_ITEM_LIMIT,
        ),
        "include_resolved": _parse_optional_boolean_argument(
            raw_arguments.get("includeResolved"),
            field_name="includeResolved",
        ),
        "include_order_book": include_order_book,
        "depth_limit": depth_limit,
    }


def execute_prediction_markets_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    service = DigitalOraclePhase1Service(
        prediction_market_providers=create_prediction_market_providers(),
    )
    result = service.lookup_prediction_markets(
        DigitalOraclePredictionMarketsQuery(
            query=cast(str, arguments["query"]),
            venues=cast(tuple[PredictionMarketVenue, ...] | None, arguments["venues"]),
            item_limit=cast(int | None, arguments["item_limit"]),
            include_resolved=cast(bool, arguments["include_resolved"]),
            include_order_book=cast(bool, arguments["include_order_book"]),
            depth_limit=cast(int | None, arguments["depth_limit"]),
        )
    )
    runtime_result = map_prediction_markets_result(result)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(f"OpenAI response requested {function_name} with invalid JSON arguments."),
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


def _parse_required_query_argument(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} query is required.",
        )
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} query must not be empty."),
        )
    return normalized


def _parse_venues_argument(value: object) -> tuple[PredictionMarketVenue, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} "
                "venues must be an array of strings."
            ),
        )
    venues: list[PredictionMarketVenue] = []
    seen: set[PredictionMarketVenue] = set()
    for raw_venue in cast(list[object], value):
        if not isinstance(raw_venue, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    "venues must be an array of strings."
                ),
            )
        venue = cast(PredictionMarketVenue, raw_venue.strip().lower())
        if venue not in _PREDICTION_MARKET_VENUES:
            allowed_values_text = ", ".join(sorted(_PREDICTION_MARKET_VENUES))
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    f"venues must use: {allowed_values_text}."
                ),
            )
        if venue not in seen:
            venues.append(venue)
            seen.add(venue)
    if not venues:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} "
                "venues must contain at least one venue."
            ),
        )
    return tuple(venues)


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


def _parse_optional_boolean_argument(value: object, *, field_name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a boolean."
            ),
        )
    return value


def _map_polymarket_event(
    raw_event: Mapping[str, object],
    *,
    query: DigitalOraclePredictionMarketsProviderQuery,
    http_client: _PredictionMarketsJsonClient,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketEvent | None:
    slug = _text(raw_event.get("slug"))
    title = _text(raw_event.get("title")) or _text(raw_event.get("name")) or slug
    event_id = _text(raw_event.get("id")) or _text(raw_event.get("eventId")) or slug
    if event_id is None or title is None:
        warnings.append(_malformed_warning("polymarket", "event identity"))
        return None
    tag_slug = _text(raw_event.get("tagSlug")) or _text(raw_event.get("tag_slug"))
    if not _matches_query(query.query, title, slug or "", tag_slug or ""):
        return None

    try:
        raw_markets = _json_array(raw_event.get("markets"))
    except ValueError:
        warnings.append(_malformed_warning("polymarket", "markets", event_id=event_id))
        return None

    contracts: list[DigitalOraclePredictionMarketContract] = []
    open_interest = _decimal(raw_event.get("openInterest"))
    for raw_market in raw_markets:
        if not isinstance(raw_market, Mapping):
            warnings.append(_malformed_warning("polymarket", "market row", event_id=event_id))
            continue
        contract = _map_polymarket_market(
            cast(Mapping[str, object], raw_market),
            event_id=event_id,
            event_open_interest=open_interest,
            query=query,
            http_client=http_client,
            warnings=warnings,
        )
        if contract is not None:
            contracts.append(contract)
    if not contracts:
        warnings.append(_malformed_warning("polymarket", "binary contracts", event_id=event_id))
        return None

    return DigitalOraclePredictionMarketEvent(
        venue="polymarket",
        event_id=event_id,
        title=title,
        status=_polymarket_status(raw_event),
        url=f"https://polymarket.com/event/{slug}" if slug is not None else None,
        end_date=_iso_datetime(_text(raw_event.get("endDate"))),
        contracts=tuple(contracts),
    )


def _map_polymarket_market(
    raw_market: Mapping[str, object],
    *,
    event_id: str,
    event_open_interest: Decimal | None,
    query: DigitalOraclePredictionMarketsProviderQuery,
    http_client: _PredictionMarketsJsonClient,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketContract | None:
    try:
        outcomes = _json_array(raw_market.get("outcomes"))
        prices = _json_array(raw_market.get("outcomePrices"))
    except ValueError:
        warnings.append(_malformed_warning("polymarket", "market outcomes", event_id=event_id))
        return None

    outcome_prices = {
        str(outcome).strip().lower(): _decimal(prices[index])
        for index, outcome in enumerate(outcomes)
        if index < len(prices)
    }
    if "yes" not in outcome_prices:
        return None
    yes_price = outcome_prices.get("yes")
    no_price = outcome_prices.get("no")
    if no_price is None and yes_price is not None:
        no_price = Decimal("1") - yes_price

    contract_id = (
        _text(raw_market.get("id"))
        or _text(raw_market.get("conditionId"))
        or _text(raw_market.get("slug"))
        or _first_text_from_json_array(raw_market.get("clobTokenIds"))
        or _first_text_from_json_array(raw_market.get("outcomeTokenIds"))
    )
    title = _text(raw_market.get("question"))
    if contract_id is None or title is None:
        warnings.append(_malformed_warning("polymarket", "market identity", event_id=event_id))
        return None
    order_book = None
    if query.include_order_book:
        token_id = _polymarket_yes_token_id(raw_market, outcomes)
        order_book = _fetch_polymarket_order_book(
            http_client,
            token_id=token_id,
            query=query,
            event_id=event_id,
            contract_id=contract_id,
            warnings=warnings,
        )
        if order_book is None:
            order_book = _map_provider_order_book(
                raw_market,
                provider="polymarket",
                event_id=event_id,
                contract_id=contract_id,
                depth_limit=query.depth_limit,
                warnings=warnings,
            )
    return DigitalOraclePredictionMarketContract(
        contract_id=contract_id,
        title=title,
        probability=yes_price,
        yes_price=yes_price,
        no_price=no_price,
        volume=_first_decimal(
            raw_market,
            ("volumeNum", "volume24hr", "volume_24hr", "volume"),
        ),
        open_interest=_first_decimal(raw_market, ("openInterest", "open_interest"))
        or event_open_interest,
        order_book=order_book,
    )


def _map_kalshi_market(
    raw_market: Mapping[str, object],
    *,
    query: DigitalOraclePredictionMarketsProviderQuery,
    http_client: _PredictionMarketsJsonClient,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketEvent | None:
    ticker = _text(raw_market.get("ticker"))
    title = _first_text(raw_market, ("title", "event_title", "series_title"))
    event_ticker = _text(raw_market.get("event_ticker")) or _text(raw_market.get("eventTicker"))
    if ticker is None or title is None:
        warnings.append(_malformed_warning("kalshi", "market identity"))
        return None
    if not _matches_query(query.query, ticker, event_ticker or "", title):
        return None

    yes_bid = _kalshi_price_decimal(
        raw_market,
        fixed_point_keys=("yes_bid_dollars", "yesBidDollars", "yes_bid_fp", "yesBidFp"),
        legacy_cent_key="yes_bid",
    )
    yes_ask = _kalshi_price_decimal(
        raw_market,
        fixed_point_keys=("yes_ask_dollars", "yesAskDollars", "yes_ask_fp", "yesAskFp"),
        legacy_cent_key="yes_ask",
    )
    no_ask = _kalshi_price_decimal(
        raw_market,
        fixed_point_keys=("no_ask_dollars", "noAskDollars", "no_ask_fp", "noAskFp"),
        legacy_cent_key="no_ask",
    )
    last_price = _kalshi_price_decimal(
        raw_market,
        fixed_point_keys=(
            "last_price_dollars",
            "lastPriceDollars",
            "last_price_fp",
            "lastPriceFp",
        ),
        legacy_cent_key="last_price",
    )
    probability = _midpoint(yes_bid, yes_ask)
    if probability is None:
        probability = last_price
    order_book = None
    if query.include_order_book:
        order_book = _fetch_kalshi_order_book(
            http_client,
            query=query,
            event_id=event_ticker or ticker,
            contract_id=ticker,
            warnings=warnings,
        )
        if order_book is None:
            order_book = _map_provider_order_book(
                raw_market,
                provider="kalshi",
                event_id=event_ticker or ticker,
                contract_id=ticker,
                depth_limit=query.depth_limit,
                fallback_bid=yes_bid,
                fallback_ask=yes_ask,
                warnings=warnings,
            )
    contract = DigitalOraclePredictionMarketContract(
        contract_id=ticker,
        title=_first_text(raw_market, ("yes_sub_title", "yesSubTitle", "subtitle")) or title,
        probability=probability,
        yes_price=yes_ask if yes_ask is not None else probability,
        no_price=no_ask,
        volume=_decimal(raw_market.get("volume")),
        open_interest=_first_decimal(raw_market, ("open_interest", "openInterest")),
        order_book=order_book,
    )
    close_time = _first_text(
        raw_market,
        ("close_time", "closeTime", "close_date", "closeDate", "expiration_time"),
    )
    return DigitalOraclePredictionMarketEvent(
        venue="kalshi",
        event_id=event_ticker or ticker,
        title=title,
        status=_text(raw_market.get("status")) or "unknown",
        url=f"https://kalshi.com/markets/{ticker}",
        end_date=_iso_datetime(close_time),
        contracts=(contract,),
    )


def _http_status_provider_error(
    exc: httpx.HTTPStatusError,
    *,
    provider: PredictionMarketVenue,
) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            f"{provider} rate limited prediction markets",
            code="provider_rate_limited",
            details={"provider": provider, "status": str(status_code)},
        )
    if status_code >= 500:
        return DigitalOracleProviderError(
            f"{provider} outage while fetching prediction markets",
            code="provider_unavailable",
            details={"provider": provider, "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        f"{provider} failed while fetching prediction markets",
        details={"provider": provider, "status": str(status_code)},
    )


def _compact_params(params: Mapping[str, object]) -> dict[str, str | int | float | bool]:
    compact: dict[str, str | int | float | bool] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            compact[key] = value
        else:
            compact[key] = str(value)
    return compact


def _object_payload(payload: object, *, provider: PredictionMarketVenue) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError(
            f"{provider} returned malformed prediction-market data",
            details={"provider": provider},
        )
    return cast(Mapping[str, object], payload)


def _object_list_payload(payload: object, *, provider: PredictionMarketVenue) -> list[object]:
    if not isinstance(payload, list):
        raise DigitalOracleProviderError(
            f"{provider} returned malformed prediction-market data",
            details={"provider": provider},
        )
    return list(cast(list[object], payload))


def _object_list(value: object) -> list[object]:
    return list(cast(list[object], value)) if isinstance(value, list) else []


def _first_text(payload: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _text(payload.get(key))
        if value is not None:
            return value
    return None


def _first_decimal(payload: Mapping[str, object], keys: tuple[str, ...]) -> Decimal | None:
    for key in keys:
        value = _decimal(payload.get(key))
        if value is not None:
            return value
    return None


def _first_text_from_json_array(value: object) -> str | None:
    try:
        values = _json_array(value)
    except ValueError:
        return None
    for item in values:
        text = _text(item)
        if text is not None:
            return text
    return None


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(cast(list[object], value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        decoded = cast(object, json.loads(text))
        if isinstance(decoded, list):
            return list(cast(list[object], decoded))
        raise ValueError("expected JSON array")
    return []


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _cent_decimal(value: object) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None:
        return None
    return parsed / Decimal("100")


def _kalshi_price_decimal(
    payload: Mapping[str, object],
    *,
    fixed_point_keys: tuple[str, ...],
    legacy_cent_key: str,
) -> Decimal | None:
    fixed_point_value = _first_decimal(payload, fixed_point_keys)
    if fixed_point_value is not None:
        return fixed_point_value
    return _cent_decimal(payload.get(legacy_cent_key))


def _midpoint(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return (left + right) / Decimal("2")


def _polymarket_yes_token_id(
    raw_market: Mapping[str, object],
    outcomes: list[object],
) -> str | None:
    yes_index = 0
    for index, outcome in enumerate(outcomes):
        if str(outcome).strip().lower() == "yes":
            yes_index = index
            break
    for key in ("clobTokenIds", "outcomeTokenIds", "clob_token_ids", "outcome_token_ids"):
        try:
            token_ids = _json_array(raw_market.get(key))
        except ValueError:
            return None
        if yes_index < len(token_ids):
            token_id = _text(token_ids[yes_index])
            if token_id is not None:
                return token_id
    return None


def _fetch_polymarket_order_book(
    http_client: _PredictionMarketsJsonClient,
    *,
    token_id: str | None,
    query: DigitalOraclePredictionMarketsProviderQuery,
    event_id: str,
    contract_id: str,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketOrderBook | None:
    if token_id is None:
        warnings.append(
            _order_book_warning(
                "polymarket",
                "prediction_markets_order_book_unavailable",
                "did not provide a prediction-market orderbook token id",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
        return None
    payload = _fetch_order_book_payload(
        http_client,
        url=f"{_POLYMARKET_ORDER_BOOK_URL}?token_id={token_id}",
        params={},
        query=query,
        provider="polymarket",
        event_id=event_id,
        contract_id=contract_id,
        warnings=warnings,
    )
    if payload is None:
        return None
    return _map_provider_order_book(
        payload,
        provider="polymarket",
        event_id=event_id,
        contract_id=contract_id,
        depth_limit=query.depth_limit,
        warnings=warnings,
    )


def _fetch_kalshi_order_book(
    http_client: _PredictionMarketsJsonClient,
    *,
    query: DigitalOraclePredictionMarketsProviderQuery,
    event_id: str,
    contract_id: str,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketOrderBook | None:
    payload = _fetch_order_book_payload(
        http_client,
        url=f"{_KALSHI_MARKETS_URL}/{contract_id}/orderbook",
        params={},
        query=query,
        provider="kalshi",
        event_id=event_id,
        contract_id=contract_id,
        warnings=warnings,
    )
    if payload is None:
        return None
    return _map_kalshi_direct_order_book(
        payload,
        event_id=event_id,
        contract_id=contract_id,
        depth_limit=query.depth_limit,
        warnings=warnings,
    )


def _fetch_order_book_payload(
    http_client: _PredictionMarketsJsonClient,
    *,
    url: str,
    params: Mapping[str, object],
    query: DigitalOraclePredictionMarketsProviderQuery,
    provider: PredictionMarketVenue,
    event_id: str,
    contract_id: str,
    warnings: list[RuntimeToolWarning],
) -> Mapping[str, object] | None:
    try:
        payload = http_client.get_json(
            url,
            params=params,
            timeout=query.timeout_seconds,
            provider=provider,
        )
    except DigitalOracleProviderError as exc:
        warnings.append(
            _order_book_provider_error_warning(
                provider,
                exc,
                event_id=event_id,
                contract_id=contract_id,
            )
        )
        return None
    if not isinstance(payload, Mapping):
        warnings.append(
            _order_book_warning(
                provider,
                "prediction_markets_order_book_malformed",
                "returned malformed prediction-market orderbook depth",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
        return None
    return cast(Mapping[str, object], payload)


def _map_kalshi_direct_order_book(
    payload: Mapping[str, object],
    *,
    event_id: str,
    contract_id: str,
    depth_limit: int,
    warnings: list[RuntimeToolWarning],
) -> DigitalOraclePredictionMarketOrderBook | None:
    source = _nested_order_book_payload(payload)
    bids = _order_book_levels(
        _first_value(source, ("bids", "yesBids", "yes_bids")),
        depth_limit=depth_limit,
    ) or _kalshi_cent_order_book_levels(
        _first_value(source, ("yes", "yes_bid", "yesBids", "yes_bids")),
        depth_limit=depth_limit,
        invert_price=False,
    )
    asks = _order_book_levels(
        _first_value(source, ("asks", "yesAsks", "yes_asks")),
        depth_limit=depth_limit,
    ) or _kalshi_cent_order_book_levels(
        _first_value(source, ("no", "no_bid", "noBids", "no_bids")),
        depth_limit=depth_limit,
        invert_price=True,
    )
    if not bids and not asks:
        warnings.append(
            _order_book_warning(
                "kalshi",
                "prediction_markets_order_book_malformed",
                "returned malformed prediction-market orderbook depth",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
        return None
    if not bids or not asks:
        warnings.append(
            _order_book_warning(
                "kalshi",
                "prediction_markets_order_book_partial",
                "returned partial prediction-market orderbook depth",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
    return DigitalOraclePredictionMarketOrderBook(
        bids=bids,
        asks=asks,
        spread=_order_book_spread(bids, asks),
        depth_limit=depth_limit,
    )


def _map_provider_order_book(
    raw_market: Mapping[str, object],
    *,
    provider: PredictionMarketVenue,
    event_id: str,
    contract_id: str,
    depth_limit: int,
    warnings: list[RuntimeToolWarning],
    fallback_bid: Decimal | None = None,
    fallback_ask: Decimal | None = None,
) -> DigitalOraclePredictionMarketOrderBook | None:
    source = _order_book_source(raw_market)
    bids: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = ()
    asks: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...] = ()
    if source is not None:
        bids = _order_book_levels(
            _first_value(source, ("bids", "yesBids", "yes_bids", "buy")),
            depth_limit=depth_limit,
        )
        asks = _order_book_levels(
            _first_value(source, ("asks", "yesAsks", "yes_asks", "sell", "offers")),
            depth_limit=depth_limit,
        )
        if not bids and not asks:
            warnings.append(
                _order_book_warning(
                    provider,
                    "prediction_markets_order_book_malformed",
                    "returned malformed prediction-market orderbook depth",
                    event_id=event_id,
                    contract_id=contract_id,
                )
            )
            return None
    elif fallback_bid is not None or fallback_ask is not None:
        bids = _fallback_order_book_levels(fallback_bid)
        asks = _fallback_order_book_levels(fallback_ask)
    else:
        warnings.append(
            _order_book_warning(
                provider,
                "prediction_markets_order_book_unavailable",
                "did not return prediction-market orderbook depth",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
        return None

    if not bids or not asks:
        warnings.append(
            _order_book_warning(
                provider,
                "prediction_markets_order_book_partial",
                "returned partial prediction-market orderbook depth",
                event_id=event_id,
                contract_id=contract_id,
            )
        )
    return DigitalOraclePredictionMarketOrderBook(
        bids=bids,
        asks=asks,
        spread=_order_book_spread(bids, asks),
        depth_limit=depth_limit,
    )


def _order_book_source(raw_market: Mapping[str, object]) -> Mapping[str, object] | None:
    for key in ("orderBook", "orderbook", "order_book", "book", "depth"):
        value = raw_market.get(key)
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    order_book_keys = ("bids", "asks", "yesBids", "yesAsks", "yes_bids", "yes_asks")
    if any(key in raw_market for key in order_book_keys):
        return raw_market
    return None


def _nested_order_book_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("orderbook", "orderBook", "order_book", "book"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    return payload


def _order_book_levels(
    value: object,
    *,
    depth_limit: int,
) -> tuple[DigitalOraclePredictionMarketOrderBookLevel, ...]:
    levels: list[DigitalOraclePredictionMarketOrderBookLevel] = []
    for raw_level in _object_list(value):
        level = _order_book_level(raw_level)
        if level is not None:
            levels.append(level)
        if len(levels) == depth_limit:
            break
    return tuple(levels)


def _order_book_level(value: object) -> DigitalOraclePredictionMarketOrderBookLevel | None:
    if isinstance(value, Mapping):
        payload = cast(Mapping[str, object], value)
        price = _first_decimal(payload, ("price", "p", "yesPrice", "yes_price"))
        size = _first_decimal(payload, ("size", "quantity", "qty", "volume"))
    elif isinstance(value, (list, tuple)) and value:
        raw_values = list(cast(tuple[object, ...] | list[object], value))
        price = _decimal(raw_values[0])
        size = _decimal(raw_values[1]) if len(raw_values) > 1 else None
    else:
        return None
    if price is None:
        return None
    return DigitalOraclePredictionMarketOrderBookLevel(price=price, size=size)


def _kalshi_cent_order_book_levels(
    value: object,
    *,
    depth_limit: int,
    invert_price: bool,
) -> tuple[DigitalOraclePredictionMarketOrderBookLevel, ...]:
    levels: list[DigitalOraclePredictionMarketOrderBookLevel] = []
    for raw_level in _object_list(value):
        level = _kalshi_cent_order_book_level(raw_level, invert_price=invert_price)
        if level is not None:
            levels.append(level)
        if len(levels) == depth_limit:
            break
    return tuple(levels)


def _kalshi_cent_order_book_level(
    value: object,
    *,
    invert_price: bool,
) -> DigitalOraclePredictionMarketOrderBookLevel | None:
    if isinstance(value, Mapping):
        payload = cast(Mapping[str, object], value)
        price = _cent_decimal(_first_value(payload, ("price", "p", "yesPrice", "yes_price")))
        size = _decimal(_first_value(payload, ("size", "quantity", "qty", "volume")))
    elif isinstance(value, (list, tuple)) and value:
        raw_values = list(cast(tuple[object, ...] | list[object], value))
        price = _cent_decimal(raw_values[0])
        size = _decimal(raw_values[1]) if len(raw_values) > 1 else None
    else:
        return None
    if price is None:
        return None
    if invert_price:
        price = Decimal("1") - price
    return DigitalOraclePredictionMarketOrderBookLevel(price=price, size=size)


def _fallback_order_book_levels(
    price: Decimal | None,
) -> tuple[DigitalOraclePredictionMarketOrderBookLevel, ...]:
    if price is None:
        return ()
    return (DigitalOraclePredictionMarketOrderBookLevel(price=price),)


def _order_book_spread(
    bids: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...],
    asks: tuple[DigitalOraclePredictionMarketOrderBookLevel, ...],
) -> Decimal | None:
    if not bids or not asks:
        return None
    highest_bid = max(level.price for level in bids)
    lowest_ask = min(level.price for level in asks)
    return lowest_ask - highest_bid


def _first_value(payload: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        iso_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _polymarket_status(raw_event: Mapping[str, object]) -> str:
    if raw_event.get("closed") is True:
        return "closed"
    if raw_event.get("active") is True:
        return "open"
    return "unknown"


def _rank_prediction_events(
    events: list[DigitalOraclePredictionMarketEvent],
) -> list[DigitalOraclePredictionMarketEvent]:
    return sorted(events, key=_prediction_event_rank)


def _prediction_event_rank(event: DigitalOraclePredictionMarketEvent) -> tuple[int, str]:
    return (0 if event.status.lower() in {"open", "active"} else 1, event.event_id)


def _query_tokens(query: str) -> tuple[str, ...]:
    return tuple(_QUERY_TOKEN_RE.findall(query.lower()))


def _matches_query(query: str, *candidates: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(candidates).lower()
    return all(token in haystack for token in tokens)


def _slug_search_term(query: str) -> str:
    return "-".join(_query_tokens(query))


def _malformed_warning(
    provider: PredictionMarketVenue,
    field: str,
    *,
    event_id: str | None = None,
) -> RuntimeToolWarning:
    details = {"operation": "prediction_markets", "provider": provider, "field": field}
    if event_id is not None:
        details["eventId"] = event_id
    return RuntimeToolWarning(
        code="prediction_markets_malformed_payload",
        message=f"{provider} returned malformed prediction-market {field}.",
        details=details,
    )


def _order_book_warning(
    provider: PredictionMarketVenue,
    code: str,
    message_fragment: str,
    *,
    event_id: str,
    contract_id: str,
) -> RuntimeToolWarning:
    return runtime_warning(
        code=code,
        message=f"{provider} {message_fragment}.",
        details={
            "operation": "prediction_markets",
            "scope": "orderbook",
            "provider": provider,
            "eventId": event_id,
            "contractId": contract_id,
        },
    )


def _order_book_provider_error_warning(
    provider: PredictionMarketVenue,
    exc: DigitalOracleProviderError,
    *,
    event_id: str,
    contract_id: str,
) -> RuntimeToolWarning:
    error_suffix = {
        "provider_timeout": "provider_timeout",
        "provider_rate_limited": "provider_rate_limited",
        "provider_unavailable": "provider_unavailable",
    }.get(exc.code, "provider_error")
    return runtime_warning(
        code=f"prediction_markets_order_book_{error_suffix}",
        message=str(exc) or f"{provider} failed while fetching prediction-market orderbook depth.",
        details={
            "operation": "prediction_markets",
            "scope": "orderbook",
            "provider": provider,
            "eventId": event_id,
            "contractId": contract_id,
            **dict(exc.details),
        },
    )


PREDICTION_MARKETS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    openai_function_name=PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Prediction Markets Lookup",
    description=_PREDICTION_MARKETS_LOOKUP_DESCRIPTION,
    parameters_schema=_PREDICTION_MARKETS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_PREDICTION_MARKETS_LOOKUP_GUIDANCE,
    sort_order=86,
    denied_code=PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_prediction_markets_lookup_arguments,
    executor=execute_prediction_markets_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "KalshiPredictionMarketsProvider",
    "PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_CODE",
    "PREDICTION_MARKETS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME",
    "PREDICTION_MARKETS_LOOKUP_TOOL_SPEC",
    "PolymarketPredictionMarketsProvider",
    "create_prediction_market_providers",
    "execute_prediction_markets_lookup",
    "parse_prediction_markets_lookup_arguments",
]
