from __future__ import annotations

import json
from typing import cast

from finance_plugin.contracts import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec
from finance_plugin.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from finance_plugin.runtime_types import REPORT_LOOKUP_TOOL_KEY
from finance_plugin.services.report_service import ReportService
from plugin_runtime.formatting import normalize_symbol

REPORT_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_finance_reports_lookup"

_REPORT_LOOKUP_DISPLAY_NAME = "Report Lookup"
_REPORT_LOOKUP_DESCRIPTION = (
    "Read persisted SignalDeck reports by ticker, tag, review type, source, limit, and offset."
)
_REPORT_LOOKUP_GUIDANCE = (
    "When you need persisted SignalDeck report context, call the "
    "signaldeck_finance_reports_lookup tool instead of inventing report content."
)
_REPORT_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "ticker": {"type": ["string", "null"]},
        "tag": {"type": ["string", "null"]},
        "reviewType": {"type": ["string", "null"]},
        "source": {
            "type": ["string", "null"],
            "enum": ["compiled", "uploaded", "external", "agent", None],
        },
        "limit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 50,
        },
        "offset": {"type": ["integer", "null"], "minimum": 0},
    },
    "required": [
        "ticker",
        "tag",
        "reviewType",
        "source",
        "limit",
        "offset",
    ],
    "unevaluatedProperties": False,
}


def parse_report_lookup_arguments(arguments_json: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "OpenAI response requested signaldeck_finance_reports_lookup with invalid "
                "JSON arguments."
            ),
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="signaldeck_finance_reports_lookup arguments must be a JSON object.",
        )
    raw_arguments = cast(dict[str, object], raw_payload)

    allowed_keys = {"ticker", "tag", "reviewType", "source", "limit", "offset"}
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "signaldeck_finance_reports_lookup arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )

    ticker = _parse_optional_string_argument(raw_arguments.get("ticker"))
    if ticker is not None:
        ticker = normalize_symbol(ticker)
    source = _parse_optional_string_argument(raw_arguments.get("source"))
    if source is not None and source not in {"compiled", "uploaded", "external", "agent"}:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                "signaldeck_finance_reports_lookup source must be one of compiled, uploaded, "
                "external, or agent."
            ),
        )
    return {
        "ticker": ticker,
        "tag": _parse_optional_string_argument(raw_arguments.get("tag")),
        "review_type": _parse_optional_string_argument(raw_arguments.get("reviewType")),
        "source": source,
        "limit": _parse_optional_integer_argument(
            raw_arguments.get("limit"),
            field_name="limit",
            minimum=1,
            maximum=50,
        )
        or 50,
        "offset": _parse_optional_integer_argument(
            raw_arguments.get("offset"),
            field_name="offset",
            minimum=0,
        )
        or 0,
    }


def execute_report_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    with context.session_factory() as session:
        reports = ReportService(session).list_reports(
            ticker=cast(str | None, arguments["ticker"]),
            tag=cast(str | None, arguments["tag"]),
            review_type=cast(str | None, arguments["review_type"]),
            source=cast(str | None, arguments["source"]),
            limit=cast(int, arguments["limit"]),
            offset=cast(int, arguments["offset"]),
        )
    return {
        "count": len(reports),
        "reports": [
            cast(dict[str, object], report.model_dump(mode="json", by_alias=True))
            for report in reports
        ],
    }


def _parse_optional_string_argument(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="signaldeck_finance_reports_lookup string arguments must be strings.",
        )
    normalized = value.strip()
    return normalized or None


def _parse_optional_integer_argument(
    value: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_finance_reports_lookup {field_name} must be an integer.",
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_finance_reports_lookup {field_name} must be at least {minimum}.",
        )
    if maximum is not None and value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"signaldeck_finance_reports_lookup {field_name} must be at most {maximum}.",
        )
    return int(value)


REPORT_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=REPORT_LOOKUP_TOOL_KEY,
    openai_function_name=REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name=_REPORT_LOOKUP_DISPLAY_NAME,
    description=_REPORT_LOOKUP_DESCRIPTION,
    parameters_schema=_REPORT_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_REPORT_LOOKUP_GUIDANCE,
    sort_order=10,
    denied_code="tool_not_granted",
    denied_message="Report lookup requires a grant",
    parser=parse_report_lookup_arguments,
    executor=execute_report_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)

__all__ = [
    "REPORT_LOOKUP_OPENAI_FUNCTION_NAME",
    "REPORT_LOOKUP_TOOL_SPEC",
    "execute_report_lookup",
    "parse_report_lookup_arguments",
]
