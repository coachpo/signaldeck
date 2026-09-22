"""Finance holders tool: one granted symbol's ownership breakdown and largest holders."""

from datetime import UTC, datetime

from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import tool

from .contracts import RuntimeToolContext, RuntimeToolWarning
from .holder_contracts import HoldersLookupInput, HoldersLookupResult, HoldersSnapshot
from .providers.quote_provider import QuoteProviderError

TOOL_NAME = "holders_lookup"
TOOL_ID = "signaldeck/finance/" + TOOL_NAME
DESCRIPTION = (
    "Read the current ownership picture of one granted symbol: the shares held by insiders "
    "and institutions and the institution count, the largest institutional and fund holders "
    "with each holder's report date, position, value and change, and insiders with their "
    "direct holdings and latest transaction. Percentages are percent of shares outstanding "
    "(percentChange is the change of the holder's position). This is the provider's current "
    "snapshot as of retrievedAt, built from the latest periodic filings; it has no history, "
    "so it cannot describe an earlier date. Disclose returned warnings."
)


def definition() -> dict:
    return tool(
        "signaldeck/finance",
        TOOL_NAME,
        {**model_wire_schema(HoldersLookupInput), "title": "查询持仓结构"},
        model_wire_schema(HoldersLookupResult),
        DESCRIPTION,
        resources=("finance-market-data",),
    )


def execute(arguments: dict, context: RuntimeToolContext, *, now: datetime | None = None) -> dict:
    payload = HoldersLookupInput.model_validate(arguments)
    provider = context.quote_provider
    warnings: list[RuntimeToolWarning] = []
    try:
        snapshot = provider.fetch_holders(payload.symbol)
    except QuoteProviderError as exc:
        snapshot = HoldersSnapshot(
            symbol=payload.symbol, provider=getattr(provider, "provider_name", "")
        )
        warnings.append(
            RuntimeToolWarning(
                code="holders_unavailable",
                message=f"Holders are unavailable for {payload.symbol}",
                details={"symbol": payload.symbol, "reason": exc.code},
            )
        )
    else:
        if snapshot.breakdown is None and not (
            snapshot.institutions or snapshot.funds or snapshot.insiders
        ):
            warnings.append(
                RuntimeToolWarning(
                    code="holders_empty",
                    message=f"The provider returned no holders for {payload.symbol}",
                    details={"symbol": payload.symbol, "provider": snapshot.provider},
                )
            )
    result = HoldersLookupResult(
        **dict(snapshot),
        retrieved_at=now or datetime.now(UTC),
        warnings=warnings,
    )
    return project(result.model_dump(mode="json", by_alias=True))
