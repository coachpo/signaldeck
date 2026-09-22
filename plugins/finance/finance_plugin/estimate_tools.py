"""Finance analyst estimates tool: consensus, estimate trends, targets and rating changes."""

from datetime import UTC, datetime

from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import tool

from .contracts import RuntimeToolContext, RuntimeToolWarning
from .estimate_contracts import (
    AnalystEstimatesLookupInput,
    AnalystEstimatesLookupResult,
    AnalystEstimatesSnapshot,
)
from .providers.quote_provider import QuoteProviderError

TOOL_NAME = "analyst_estimates_lookup"
TOOL_ID = "signaldeck/finance/" + TOOL_NAME
# One provider request per table: estimates and trends, targets, recommendations,
# earnings history and rating changes.
TIMEOUT_SECONDS = 90.0
DESCRIPTION = (
    "Read analyst consensus for one granted symbol: per period (0q current and +1q next "
    "fiscal quarter, 0y current and +1y next fiscal year, as the provider defines them at "
    "retrievedAt) the EPS and revenue estimates with their range, analyst count, year-ago "
    "value and growth percent, the EPS estimate 7, 30, 60 and 90 days ago and the count of "
    "upward and downward revisions; the price target range; buy, hold and sell "
    "recommendation counts for this month and the three before; the last reported quarters' "
    "EPS against the estimate with the surprise percent; and the newest rating changes "
    "(ratingChangeLimit, default 10, 0 omits them; ratingChangeCount counts all). This is the "
    "provider's current snapshot with no earlier versions, so it cannot tell what the "
    "consensus was on a past date. Estimates are third-party opinions, not facts or advice; "
    "disclose returned warnings."
)


def definition() -> dict:
    return {
        **tool(
            "signaldeck/finance",
            TOOL_NAME,
            {**model_wire_schema(AnalystEstimatesLookupInput), "title": "查询分析师预期"},
            model_wire_schema(AnalystEstimatesLookupResult),
            DESCRIPTION,
            resources=("finance-market-data",),
        ),
        "timeoutSeconds": TIMEOUT_SECONDS,
    }


def execute(arguments: dict, context: RuntimeToolContext, *, now: datetime | None = None) -> dict:
    payload = AnalystEstimatesLookupInput.model_validate(arguments)
    provider = context.quote_provider
    warnings: list[RuntimeToolWarning] = []
    try:
        snapshot = provider.fetch_analyst_estimates(payload.symbol)
    except QuoteProviderError as exc:
        snapshot = AnalystEstimatesSnapshot(
            symbol=payload.symbol, provider=getattr(provider, "provider_name", "")
        )
        warnings.append(
            RuntimeToolWarning(
                code="analyst_estimates_unavailable",
                message=f"Analyst estimates are unavailable for {payload.symbol}",
                details={"symbol": payload.symbol, "reason": exc.code},
            )
        )
    else:
        if not (
            snapshot.periods
            or snapshot.price_target
            or snapshot.recommendations
            or snapshot.earnings_history
            or snapshot.rating_changes
        ):
            warnings.append(
                RuntimeToolWarning(
                    code="analyst_estimates_empty",
                    message=f"The provider returned no analyst estimates for {payload.symbol}",
                    details={"symbol": payload.symbol, "provider": snapshot.provider},
                )
            )
    result = AnalystEstimatesLookupResult(
        **{
            **dict(snapshot),
            "rating_changes": snapshot.rating_changes[: payload.rating_change_limit],
        },
        rating_change_count=len(snapshot.rating_changes),
        retrieved_at=now or datetime.now(UTC),
        warnings=warnings,
    )
    return project(result.model_dump(mode="json", by_alias=True))
