from __future__ import annotations

from oracle_plugin.config import CftcPositioningReportType
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.runtime_cftc_positioning_client import (
    CftcPositioningJsonClient,
    HttpxCftcPositioningJsonClient,
)
from oracle_plugin.runtime_cftc_positioning_payloads import (
    map_rows,
    row_values,
    stale_dataset_warning,
)
from oracle_plugin.types import (
    DigitalOracleCftcPositioningProvider,
    DigitalOracleCftcPositioningProviderQuery,
    DigitalOracleCftcPositioningProviderResult,
    DigitalOracleCftcPositioningReport,
)

_CFTC_DATASET_URL_BY_REPORT_TYPE: dict[CftcPositioningReportType, str] = {
    "legacy_futures_only": "https://publicreporting.cftc.gov/resource/6dca-aqww.json",
    "legacy_combined": "https://publicreporting.cftc.gov/resource/jun7-fc8e.json",
    "disaggregated_futures_only": "https://publicreporting.cftc.gov/resource/72hh-3qpy.json",
    "disaggregated_combined": "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json",
    "financial_futures": "https://publicreporting.cftc.gov/resource/gpe5-46if.json",
}


class CftcCotPositioningProvider:
    provider_name = "cftc"

    def __init__(self, http_client: CftcPositioningJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxCftcPositioningJsonClient()

    def lookup_cftc_positioning(
        self,
        query: DigitalOracleCftcPositioningProviderQuery,
    ) -> DigitalOracleCftcPositioningProviderResult:
        reports: list[DigitalOracleCftcPositioningReport] = []
        warnings: list[RuntimeToolWarning] = []
        for report_type in query.report_types:
            payload = self._http_client.get_json(
                _CFTC_DATASET_URL_BY_REPORT_TYPE[report_type],
                params=_query_params(query, report_type=report_type),
                timeout=query.timeout_seconds,
                report_type=report_type,
            )
            mapped = map_rows(
                row_values(payload),
                provider=self.provider_name,
                report_type=report_type,
                warnings=warnings,
            )
            reports.extend(mapped.reports)
            if mapped.stale_report_dates:
                warnings.append(stale_dataset_warning(report_type, mapped.stale_report_dates))
        return DigitalOracleCftcPositioningProviderResult(
            provider=self.provider_name,
            reports=tuple(reports[: query.item_limit]),
            warnings=tuple(warnings),
        )


def create_cftc_positioning_providers() -> tuple[DigitalOracleCftcPositioningProvider, ...]:
    return (CftcCotPositioningProvider(),)


def _query_params(
    query: DigitalOracleCftcPositioningProviderQuery,
    *,
    report_type: CftcPositioningReportType,
) -> dict[str, object]:
    del report_type
    params: dict[str, object] = {"$limit": query.item_limit}
    where_clauses: list[str] = []
    if query.start_date is not None:
        where_clauses.append(f"report_date_as_yyyy_mm_dd >= '{query.start_date.isoformat()}'")
    if query.end_date is not None:
        where_clauses.append(f"report_date_as_yyyy_mm_dd <= '{query.end_date.isoformat()}'")
    if query.markets:
        market_filters = " OR ".join(
            f"upper(market_and_exchange_names) like '%{_socrata_literal(market.upper())}%'"
            for market in query.markets
        )
        where_clauses.append(f"({market_filters})")
    if where_clauses:
        params["$where"] = " AND ".join(where_clauses)
    params["$order"] = "report_date_as_yyyy_mm_dd DESC"
    return params


def _socrata_literal(value: str) -> str:
    return value.replace("'", "''")


__all__ = ["CftcCotPositioningProvider", "create_cftc_positioning_providers"]
