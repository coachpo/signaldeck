"""The published Finance K-line event tool: contract, grants and bounded results."""

import asyncio
import sys
from contextlib import nullcontext
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import get_args

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.test_durable_runtime_support import serve_app
from tests.test_independent_plugins import invocation

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin import price_event_tools  # noqa: E402
from finance_plugin.contracts import RuntimeToolContext  # noqa: E402
from finance_plugin.main import create_app  # noqa: E402
from finance_plugin.price_event_contracts import DetectorType, MeasureName  # noqa: E402
from finance_plugin.price_event_digest import MEASURE_NAMES, RULE_NAMES  # noqa: E402
from finance_plugin.providers.quote_provider import (  # noqa: E402
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    QuoteProviderError,
)

from app.domain.schema_contract import validate_schema, validate_value  # noqa: E402

TOOL = "signaldeck/finance/price_events_lookup"
JUMP = date(2026, 9, 14)
EX_DIVIDEND = date(2026, 9, 16)


class ScriptedProvider:
    """Flat weekday bars at 100 that gap up and close at 110 on JUMP, except flat symbols."""

    provider_name = "scripted"

    def __init__(self, failing: set[str] | None = None, flat: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.flat = flat or set()
        self.calls: list[tuple[str, datetime, datetime, str]] = []

    def fetch_ohlcv(self, symbol, *, start_date, end_date, interval):
        self.calls.append((symbol, start_date, end_date, interval))
        if symbol in self.failing:
            raise QuoteProviderError(f"OHLCV unavailable for {symbol}")
        rows, day = [], start_date.date()
        while day <= end_date.date():
            if day.weekday() < 5:
                jumped = symbol not in self.flat
                close = Decimal(110 if day >= JUMP and jumped else 100)
                opening = Decimal(108) if day == JUMP and jumped else close
                rows.append(
                    ProviderOhlcvRow(
                        at=datetime.combine(day, time(13, 30), UTC),
                        open=opening,
                        high=close + 1,
                        low=opening - 1,
                        close=close,
                        volume=5000 if day == JUMP and jumped else 1000,
                        adjusted_close=close,
                    )
                )
            day += timedelta(days=1)
        return ProviderOhlcvSeries(symbol=symbol, currency="USD", provider="scripted", rows=rows)


class DividendProvider:
    """Flat weekday bars at 100 that trade 2 lower from a 2 dividend on EX_DIVIDEND."""

    provider_name = "scripted"

    def __init__(self, adjusted: bool) -> None:
        self.adjusted = adjusted

    def fetch_ohlcv(self, symbol, *, start_date, end_date, interval):
        rows, day = [], start_date.date()
        while day <= end_date.date():
            if day.weekday() < 5:
                close = Decimal(98 if day >= EX_DIVIDEND else 100)
                adjusted = close * Decimal("0.98") if day < EX_DIVIDEND else close
                rows.append(
                    ProviderOhlcvRow(
                        at=datetime.combine(day, time(13, 30), UTC),
                        open=close,
                        high=close + 1,
                        low=close - 1,
                        close=close,
                        volume=5000 if day == JUMP else 1000,
                        adjusted_close=adjusted if self.adjusted else None,
                    )
                )
            day += timedelta(days=1)
        return ProviderOhlcvSeries(symbol=symbol, currency="USD", provider="scripted", rows=rows)


def grant(*symbols: str) -> dict:
    return {
        "resourceGrants": ["finance-market-data"],
        "resourceBindings": {"finance-market-data": {"allowedSymbols": list(symbols)}},
    }


def arguments(**overrides) -> dict:
    return {
        "symbols": ["MSFT"],
        "asOfDate": "2026-09-18",
        "windowSessions": 10,
        "detectors": [
            {"type": "gap"},
            {"type": "large_move"},
            {"type": "new_high_low"},
            {"type": "volume_spike"},
        ],
        **overrides,
    }


def contract(app) -> dict:
    release = next(route for route in app.routes if getattr(route, "path", "") == "/release")
    return next(tool for tool in release.endpoint()["tools"] if tool["toolId"] == TOOL)


def test_published_contract_validates_a_real_scan() -> None:
    provider = ScriptedProvider()
    app = create_app("postgresql+psycopg://localhost/unused", provider)
    published = contract(app)
    assert published["effect"] == "read"
    assert published["resourceRequirements"] == ["finance-market-data"]
    assert published["timeoutSeconds"] == 120.0
    validate_schema(published["inputSchema"])
    validate_schema(published["outputSchema"])
    validate_value(published["inputSchema"], arguments())

    result = app.state.execute(TOOL, arguments(), grant("MSFT"))

    validate_value(published["outputSchema"], result)
    assert provider.calls[0][0] == "MSFT" and provider.calls[0][3] == "1d"
    assert provider.calls[0][2] - provider.calls[0][1] == timedelta(days=740)
    assert (result["asOfDate"], result["cutoffAt"]) == ("2026-09-18", "2026-09-19T04:00:00Z")
    assert result["matchedCount"] == 4 and result["warnings"] == []
    assert (result["scannedSymbols"], result["latestSession"]) == (["MSFT"], "2026-09-18")
    assert "digest" not in result
    series = result["series"][0]
    assert (series["lastSession"], series["windowStart"], series["sessionCount"]) == (
        "2026-09-18",
        "2026-09-07",
        500,
    )
    assert series["priceBasis"] == "dividend_adjusted"
    assert [
        (event["detector"]["type"], event["direction"], event["session"])
        for event in series["events"]
    ] == [
        ("gap", "up", "2026-09-14"),
        ("large_move", "up", "2026-09-14"),
        ("new_high_low", "up", "2026-09-14"),
        ("volume_spike", "up", "2026-09-14"),
    ]
    gap, move = series["events"][0], series["events"][1]
    assert gap["detector"] == {"type": "gap", "minPercent": "1"}
    assert series["events"][2]["detector"] == {
        "type": "new_high_low",
        "lookback": 60,
        "minBaseSessions": 1,
    }
    assert (gap["close"], gap["rawClose"]) == ("110.0000", "110.0000")
    assert (gap["level"], gap["levelLabel"], gap["changePercent"]) == (
        "101.0000",
        "prior_high",
        "10.0000",
    )
    assert gap["measures"] == [
        {"name": "gapPercent", "value": "6.9307", "unit": "percent"},
        {"name": "gapAtr", "value": "3.5000", "unit": "atr"},
    ]
    assert {item["name"]: item["value"] for item in move["measures"]} == {
        "thresholdPercent": "4.0000",
        "moveAtr": "5.0000",
        "volumeRatio": "5.0000",
    }
    state = series["state"]
    assert (state["close"], state["streak"], state["maAlignment"]) == ("110.0000", 0, "bullish")
    assert state["ranges"][0] == {
        "lookback": 20,
        "highestClose": "110.0000",
        "lowestClose": "100.0000",
        "distanceFromHighPercent": "0.0000",
        "distanceFromLowPercent": "10.0000",
        "sessionsSinceHigh": 0,
        "sessionsSinceLow": 5,
    }


def test_rules_read_dividend_adjusted_prices_and_report_raw_closes() -> None:
    scan = arguments(detectors=[{"type": "gap"}, {"type": "volume_spike"}])

    def scanned(adjusted: bool) -> dict:
        app = create_app("postgresql+psycopg://localhost/unused", DividendProvider(adjusted))
        result = app.state.execute(TOOL, scan, grant("MSFT"))
        validate_value(contract(app)["outputSchema"], result)
        return result

    adjusted = scanned(True)
    series = adjusted["series"][0]
    assert (series["priceBasis"], adjusted["warnings"]) == ("dividend_adjusted", [])
    assert [
        (event["detector"]["type"], event["session"], event["close"], event["rawClose"])
        for event in series["events"]
    ] == [("volume_spike", "2026-09-14", "98.0000", "100.0000")]
    assert series["state"]["ranges"][0]["highestClose"] == "98.0000"

    unadjusted = scanned(False)
    series = unadjusted["series"][0]
    assert series["priceBasis"] == "split_adjusted"
    assert [
        (event["detector"]["type"], event["direction"], event["session"], event["rawClose"])
        for event in series["events"]
    ] == [
        ("gap", "down", "2026-09-16", "98.0000"),
        ("volume_spike", "neutral", "2026-09-14", "100.0000"),
    ]
    assert series["state"]["ranges"][0]["highestClose"] == "100.0000"
    assert [(item["code"], item["details"]) for item in unadjusted["warnings"]] == [
        ("price_events_dividend_unadjusted", [{"key": "symbol", "value": "MSFT"}])
    ]


def test_watchlist_scan_covers_every_granted_symbol_and_reports_only_events() -> None:
    app = create_app("postgresql+psycopg://localhost/unused", ScriptedProvider(flat={"KO"}))
    scan = {
        "asOfDate": "2026-09-18",
        "windowSessions": 10,
        "detectors": [{"type": "gap"}],
        "includeDigest": True,
    }
    result = app.state.execute(TOOL, scan, grant("msft", "KO", "SPY", "MSFT"))
    validate_value(contract(app)["outputSchema"], result)
    assert (result["scannedSymbols"], result["latestSession"]) == (
        ["MSFT", "KO", "SPY"],
        "2026-09-18",
    )
    assert [item["symbol"] for item in result["series"]] == ["MSFT", "SPY"]
    assert result["matchedCount"] == 2 and result["warnings"] == []
    row = (
        "| 2026-09-14 | 跳空缺口 | 向上 | 110.00 | +10.00% "
        "| 参考价 101.00，缺口 6.93%，缺口折合 3.50 ATR |"
    )
    assert result["digest"] == "\n".join(
        [
            "# K 线事件 · 2026-09-18",
            "",
            "扫描 3 只证券，最新完成交易日 2026-09-18；2 只证券共 2 个事件。",
            "",
            "| 证券 | 交易日 | 事件 | 方向 | 收盘 | 涨跌幅 | 要点 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            "| MSFT " + row,
            "| SPY " + row,
            "",
            "规则：gap(minPercent=1)",
            "",
            "按分红复权价格识别事件（缺少复权数据的证券见提示）；收盘列是 provider 原始收盘价，"
            "涨跌幅按识别所用的价格计算。",
            "",
            "事件只描述历史价格，不构成预测或交易建议。",
        ]
    )
    for scope, code in [
        (grant(), "price_events_no_granted_symbols"),
        (grant(*(f"S{index}" for index in range(51))), "price_events_watchlist_too_large"),
        (
            {"resourceGrants": [], "resourceBindings": {}},
            "finance_resource_not_granted",
        ),
    ]:
        with pytest.raises(ValueError, match=code):
            app.state.execute(TOOL, scan, scope)


def test_watchlist_scan_warns_once_for_an_unadjusted_benchmark() -> None:
    app = create_app("postgresql+psycopg://localhost/unused", DividendProvider(adjusted=False))
    scan = {
        "asOfDate": "2026-09-18",
        "windowSessions": 5,
        "detectors": [{"type": "relative_strength", "benchmark": "SPY"}],
    }
    result = app.state.execute(TOOL, scan, grant("MSFT", "SPY"))
    assert (result["scannedSymbols"], result["series"]) == (["MSFT", "SPY"], [])
    assert [(item["code"], item["details"]) for item in result["warnings"]] == [
        ("price_events_dividend_unadjusted", [{"key": "symbol", "value": symbol}])
        for symbol in ("MSFT", "SPY")
    ]


def test_digest_notes_a_date_without_a_completed_session() -> None:
    context = RuntimeToolContext(nullcontext, ScriptedProvider(flat={"KO"}))
    result = price_event_tools.execute(
        {
            "asOfDate": "2026-09-19",
            "windowSessions": 1,
            "detectors": [{"type": "gap"}],
            "includeDigest": True,
        },
        grant("KO"),
        context,
        now=datetime(2026, 9, 19, 21, tzinfo=UTC),
    )
    assert (result["latestSession"], result["series"], result["matchedCount"]) == (
        "2026-09-18",
        [],
        0,
    )
    assert result["digest"].split("\n")[2:4] == [
        "扫描 1 只证券，最新完成交易日 2026-09-18；未发现所选事件。",
        "2026-09-19 没有已完成的交易日：当天休市或尚未收盘。",
    ]


def test_digest_names_every_rule_and_measure() -> None:
    assert set(RULE_NAMES) == set(get_args(DetectorType))
    assert set(MEASURE_NAMES) == set(get_args(MeasureName))


def test_symbols_and_benchmark_must_be_granted() -> None:
    app = create_app("postgresql+psycopg://localhost/unused", ScriptedProvider())
    benchmark = arguments(detectors=[{"type": "relative_strength", "benchmark": "SPY"}])
    for payload, scope, code in [
        (arguments(symbols=["AAPL"]), grant("MSFT"), "finance_symbol_not_granted"),
        (benchmark, grant("MSFT"), "finance_symbol_not_granted"),
        (
            arguments(),
            {"resourceGrants": [], "resourceBindings": {}},
            "finance_resource_not_granted",
        ),
    ]:
        with pytest.raises(ValueError, match=code):
            app.state.execute(TOOL, payload, scope)
    result = app.state.execute(TOOL, benchmark, grant("MSFT", "SPY"))
    assert [item["symbol"] for item in result["series"]] == ["MSFT"]


def test_sessions_count_only_after_the_new_york_settlement_time() -> None:
    context = RuntimeToolContext(nullcontext, ScriptedProvider())
    scan = {key: value for key, value in arguments().items() if key != "asOfDate"}

    def last_session(now: datetime) -> tuple[str, str]:
        result = price_event_tools.execute(scan, grant("MSFT"), context, now=now)
        return result["asOfDate"], result["series"][0]["lastSession"]

    assert last_session(datetime(2026, 9, 18, 20, 29, tzinfo=UTC)) == ("2026-09-18", "2026-09-17")
    assert last_session(datetime(2026, 9, 18, 20, 30, tzinfo=UTC)) == ("2026-09-18", "2026-09-18")
    with pytest.raises(ValueError, match="price_events_date_in_future"):
        price_event_tools.execute(
            arguments(asOfDate="2026-09-19"),
            grant("MSFT"),
            context,
            now=datetime(2026, 9, 18, 21, tzinfo=UTC),
        )


def test_unavailable_symbols_and_truncated_events_are_reported() -> None:
    app = create_app("postgresql+psycopg://localhost/unused", ScriptedProvider({"AAPL"}))
    result = app.state.execute(
        TOOL,
        arguments(
            symbols=["MSFT", "AAPL"],
            windowSessions=120,
            detectors=[{"type": "volume_spike", "volumeRatio": "0.01"}],
            includeDigest=True,
        ),
        grant("MSFT", "AAPL"),
    )
    validate_value(contract(app)["outputSchema"], result)
    series = result["series"]
    assert [item["symbol"] for item in series] == ["MSFT"]
    assert (result["matchedCount"], series[0]["eventCount"], len(series[0]["events"])) == (
        120,
        120,
        50,
    )
    assert series[0]["events"][0]["session"] == "2026-09-18"
    assert [warning["code"] for warning in result["warnings"]] == [
        "ohlcv_unavailable",
        "price_events_truncated",
    ]
    digest = result["digest"].split("\n")
    assert "MSFT 另有 70 个较早的事件未列出。" in digest
    assert digest[digest.index("提示：") + 1 :][:2] == [
        "- No OHLCV data available for AAPL",
        "- 120 events found for MSFT; the latest 50 returned",
    ]


def test_scan_round_trips_through_real_mcp_with_closed_arguments(database_url):
    app = create_app(database_url, ScriptedProvider())
    context = {**invocation(TOOL), **grant("MSFT")}

    async def scenario():
        async with app.router.lifespan_context(app):
            async with serve_app(app) as url:
                async with streamable_http_client(url + "/mcp/") as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        release = (await session.list_tools()).meta["signaldeck/release"]
                        meta = {"signaldeck/release": release, "signaldeck/context": context}
                        scanned = await session.call_tool(TOOL, arguments(), meta=meta)
                        assert not scanned.isError, scanned
                        assert scanned.structuredContent["matchedCount"] == 4
                        for detector in ({"type": "gap", "window": 5}, {"type": "gap", "x": 1}):
                            loose = arguments(detectors=[detector])
                            rejected = await session.call_tool(TOOL, loose, meta=meta)
                            assert rejected.isError

    try:
        asyncio.run(scenario())
    finally:
        app.state.engine.dispose()
