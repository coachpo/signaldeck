"""The published Finance holders and analyst estimates tools: contracts, grants and warnings."""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.test_durable_runtime_support import serve_app
from tests.test_independent_plugins import invocation

for directory in ("runtime", "finance"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / directory))

from finance_plugin import estimate_tools, holder_tools  # noqa: E402
from finance_plugin.estimate_contracts import (  # noqa: E402
    AnalystEstimatesSnapshot,
    RatingChange,
)
from finance_plugin.holder_contracts import HoldersSnapshot  # noqa: E402
from finance_plugin.main import create_app  # noqa: E402
from finance_plugin.providers.quote_provider import (  # noqa: E402
    DeterministicQuoteProvider,
    QuoteProviderError,
)

from app.domain.schema_contract import validate_schema, validate_value  # noqa: E402

NOW = datetime(2026, 9, 22, 12, tzinfo=UTC)


class FailingProvider:
    provider_name = "failing"

    def fetch_holders(self, symbol):
        raise QuoteProviderError("Provider request failed", code="provider_timeout")

    def fetch_analyst_estimates(self, symbol):
        raise QuoteProviderError("Provider request failed", code="provider_timeout")


class EmptyProvider:
    provider_name = "empty"

    def fetch_holders(self, symbol):
        return HoldersSnapshot(symbol=symbol, provider="empty")

    def fetch_analyst_estimates(self, symbol):
        return AnalystEstimatesSnapshot(
            symbol=symbol,
            provider="empty",
            rating_changes=[
                RatingChange(at=datetime(2026, 9, day, tzinfo=UTC), firm=f"Firm {day}")
                for day in (18, 17, 16)
            ],
        )


def published(app, tool_id: str) -> dict:
    release = next(route for route in app.routes if getattr(route, "path", "") == "/release")
    return next(tool for tool in release.endpoint()["tools"] if tool["toolId"] == tool_id)


def grant(*symbols: str) -> dict:
    return {
        "resourceGrants": ["finance-market-data"],
        "resourceBindings": {"finance-market-data": {"allowedSymbols": list(symbols)}},
    }


def test_published_contracts_accept_deterministic_results() -> None:
    provider = DeterministicQuoteProvider()
    app = create_app("postgresql+psycopg://localhost/unused", provider)
    context = SimpleNamespace(quote_provider=provider)
    for module, arguments, timeout in (
        (holder_tools, {"symbol": "MSFT"}, 30.0),
        (estimate_tools, {"symbol": "MSFT", "ratingChangeLimit": 5}, 90.0),
    ):
        contract = published(app, module.TOOL_ID)
        assert contract["effect"] == "read"
        assert contract["resourceRequirements"] == ["finance-market-data"]
        assert contract["timeoutSeconds"] == timeout
        validate_schema(contract["inputSchema"])
        validate_schema(contract["outputSchema"])
        validate_value(contract["inputSchema"], arguments)
        result = module.execute(arguments, context, now=NOW)
        validate_value(contract["outputSchema"], result)
        assert result["retrievedAt"] == "2026-09-22T12:00:00Z"
        assert result["warnings"] == []

    holders = holder_tools.execute({"symbol": "msft"}, context, now=NOW)
    assert holders["symbol"] == "MSFT"
    assert holders["breakdown"]["institutionsPercent"] == "60.2"
    assert holders["institutions"][0]["reportDate"] == "2024-03-31"


def test_provider_failures_and_empty_snapshots_become_warnings() -> None:
    failing = SimpleNamespace(quote_provider=FailingProvider())
    holders = holder_tools.execute({"symbol": "MSFT"}, failing, now=NOW)
    assert (holders["provider"], holders["institutions"]) == ("failing", [])
    assert holders["warnings"][0]["code"] == "holders_unavailable"
    assert {"key": "reason", "value": "provider_timeout"} in holders["warnings"][0]["details"]
    estimates = estimate_tools.execute({"symbol": "MSFT"}, failing, now=NOW)
    assert (estimates["periods"], estimates["ratingChangeCount"]) == ([], 0)
    assert estimates["warnings"][0]["code"] == "analyst_estimates_unavailable"

    empty = SimpleNamespace(quote_provider=EmptyProvider())
    holders = holder_tools.execute({"symbol": "MSFT"}, empty, now=NOW)
    assert [warning["code"] for warning in holders["warnings"]] == ["holders_empty"]
    assert "breakdown" not in holders


def test_rating_changes_follow_the_limit_and_count_every_change() -> None:
    empty = SimpleNamespace(quote_provider=EmptyProvider())
    limited = estimate_tools.execute({"symbol": "MSFT", "ratingChangeLimit": 2}, empty, now=NOW)
    assert [change["firm"] for change in limited["ratingChanges"]] == ["Firm 18", "Firm 17"]
    assert limited["ratingChangeCount"] == 3
    # Rating changes alone are provider data, so no empty-result warning is raised.
    assert limited["warnings"] == []
    omitted = estimate_tools.execute({"symbol": "MSFT", "ratingChangeLimit": 0}, empty, now=NOW)
    assert (omitted["ratingChanges"], omitted["ratingChangeCount"]) == ([], 3)


def test_tools_round_trip_through_real_mcp_with_symbol_grants(database_url):
    app = create_app(database_url, DeterministicQuoteProvider())

    async def scenario():
        async with app.router.lifespan_context(app):
            async with serve_app(app) as url:
                async with streamable_http_client(url + "/mcp/") as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        release = (await session.list_tools()).meta["signaldeck/release"]
                        for module in (holder_tools, estimate_tools):
                            context = {**invocation(module.TOOL_ID), **grant("MSFT")}
                            meta = {"signaldeck/release": release, "signaldeck/context": context}
                            called = await session.call_tool(
                                module.TOOL_ID, {"symbol": "MSFT"}, meta=meta
                            )
                            assert not called.isError, called
                            assert called.structuredContent["symbol"] == "MSFT"
                            for rejected_arguments in (
                                {"symbol": "AAPL"},
                                {"symbol": "MSFT", "x": 1},
                            ):
                                rejected = await session.call_tool(
                                    module.TOOL_ID, rejected_arguments, meta=meta
                                )
                                assert rejected.isError

    try:
        asyncio.run(scenario())
    finally:
        app.state.engine.dispose()
