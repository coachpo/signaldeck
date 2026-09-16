"""Kalshi fixed-point prices and contract counts retain their published units."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin.config import reset_digital_oracle_settings_cache  # noqa: E402
from oracle_plugin.contracts import RuntimeToolContext  # noqa: E402
from oracle_plugin.runtime_prediction_markets import (  # noqa: E402
    execute_prediction_markets_lookup,
    parse_prediction_markets_lookup_arguments,
)


@pytest.fixture
def mock_kalshi(monkeypatch: pytest.MonkeyPatch):
    client_class = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        monkeypatch.setattr(
            "oracle_plugin.runtime_prediction_markets.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    reset_digital_oracle_settings_cache()
    yield install
    reset_digital_oracle_settings_cache()


def _lookup(mock_kalshi, *, market=None, orderbook=None, depth_limit=1):
    market_payload = {
        "ticker": "KXFEDCUT-26",
        "event_ticker": "KXFEDCUT",
        "title": "Fed cut odds",
        "status": "open",
        "yes_bid_dollars": "0.5500",
        "yes_ask_dollars": "0.5700",
        **(market or {}),
    }

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.elections.kalshi.com"
        if request.url.path == "/trade-api/v2/markets":
            return httpx.Response(200, json={"markets": [market_payload]})
        assert request.url.path == "/trade-api/v2/markets/KXFEDCUT-26/orderbook"
        assert orderbook is not None
        return httpx.Response(200, json=orderbook)

    mock_kalshi(respond)
    return execute_prediction_markets_lookup(
        RuntimeToolContext(),
        parse_prediction_markets_lookup_arguments(
            json.dumps(
                {
                    "query": "Fed cut",
                    "venues": ["kalshi"],
                    "includeOrderBook": orderbook is not None,
                    **({"depthLimit": depth_limit} if orderbook is not None else {}),
                }
            )
        ),
    )


@pytest.mark.parametrize("count", ["123.75", "0.00", "9007199254740993.25"])
def test_kalshi_fixed_point_counts_take_precedence_without_unit_conversion(mock_kalshi, count):
    payload = _lookup(
        mock_kalshi,
        market={"volume_fp": count, "open_interest_fp": count, "volume": 99, "open_interest": 99},
    )
    contract = payload["events"][0]["contracts"][0]
    assert contract["volume"] == count
    assert contract["openInterest"] == count
    assert payload["warnings"] == []


@pytest.mark.parametrize("depth_limit", [1, 2])
def test_kalshi_dollar_orderbook_selects_best_prices_before_depth_limit(mock_kalshi, depth_limit):
    payload = _lookup(
        mock_kalshi,
        depth_limit=depth_limit,
        orderbook={
            "orderbook_fp": {
                "yes_dollars": [["0.1500", "10.50"], ["0.5400", "3.75"], ["0.5515", "100.25"]],
                "no_dollars": [["0.3000", "2.50"], ["0.4100", "5.00"], ["0.4295", "1.25"]],
            }
        },
    )
    book = payload["events"][0]["contracts"][0]["orderBook"]
    assert (
        book["bids"]
        == [
            {"price": "0.5515", "size": "100.25"},
            {"price": "0.5400", "size": "3.75"},
        ][:depth_limit]
    )
    assert (
        book["asks"]
        == [
            {"price": "0.5705", "size": "1.25"},
            {"price": "0.5900", "size": "5.00"},
        ][:depth_limit]
    )
    assert book["spread"] == "0.0190"
    assert book["depthLimit"] == depth_limit
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "orderbook",
    [
        {"yes": [[20, 10], [55, "100.25"]], "no": [[30, 20], [43, "75.50"]]},
        {"bids": [["0.20", 10], ["0.55", "100.25"]], "asks": [["0.70", 20], ["0.57", "75.50"]]},
    ],
)
def test_kalshi_existing_orderbook_shapes_keep_units_and_select_best_depth(mock_kalshi, orderbook):
    payload = _lookup(mock_kalshi, orderbook={"orderbook": orderbook})
    book = payload["events"][0]["contracts"][0]["orderBook"]
    assert book["bids"] == [{"price": "0.55", "size": "100.25"}]
    assert book["asks"] == [{"price": "0.57", "size": "75.50"}]
    assert book["spread"] == "0.02"
    assert payload["warnings"] == []


def test_kalshi_empty_fixed_point_side_is_not_filled_from_legacy_orderbook(mock_kalshi):
    payload = _lookup(
        mock_kalshi,
        orderbook={
            "orderbook_fp": {"yes_dollars": [], "no_dollars": [["0.4500", "8.25"]]},
            "orderbook": {"yes": [[80, 30]], "no": [[10, 30]]},
        },
    )
    book = payload["events"][0]["contracts"][0]["orderBook"]
    assert book["bids"] == []
    assert book["asks"] == [{"price": "0.5500", "size": "8.25"}]
    assert book["spread"] is None
    assert [warning["code"] for warning in payload["warnings"]] == [
        "prediction_markets_order_book_partial"
    ]


def test_kalshi_malformed_prices_do_not_displace_valid_depth(mock_kalshi):
    payload = _lookup(
        mock_kalshi,
        orderbook={
            "orderbook_fp": {
                "yes_dollars": [["NaN", "9"], ["bad", "9"], ["0.5000", "12.50"]],
                "no_dollars": [["Infinity", "9"], ["0.4000", "10.25"]],
            }
        },
    )
    book = payload["events"][0]["contracts"][0]["orderBook"]
    assert book["bids"] == [{"price": "0.5000", "size": "12.50"}]
    assert book["asks"] == [{"price": "0.6000", "size": "10.25"}]
    assert book["spread"] == "0.1000"
