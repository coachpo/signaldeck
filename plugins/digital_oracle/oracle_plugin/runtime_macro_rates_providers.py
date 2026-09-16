from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from urllib.parse import quote, unquote

from oracle_plugin.config import MacroRatesSource
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.runtime_macro_rates_client import HttpxMacroRatesJsonClient, MacroRatesJsonClient
from oracle_plugin.runtime_macro_rates_payloads import MacroRatesRowDefaults, map_rows, row_values
from oracle_plugin.types import (
    DigitalOracleMacroRatesProvider,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
    DigitalOracleProviderError,
)
from oracle_plugin.warnings import runtime_warning

_FRED_SERIES_URL = "https://api.stlouisfed.org/fred/series"
_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
_TREASURY_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
_TREASURY_FILTER_PAGE_SIZE = 100
_TREASURY_FILTER_MAX_PAGES = 10
_BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL_D"
_WORLDBANK_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.KD.ZG"
_CME_FEDWATCH_URL = "https://www.cmegroup.com/CmeWS/mvc/FedWatch/Tool/UpcomingFOMCMeetings"


class FredMacroRatesProvider:
    source: MacroRatesSource = "fred"

    def __init__(self, http_client: MacroRatesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxMacroRatesJsonClient()

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        rows = []
        warnings: list[RuntimeToolWarning] = []
        end_date = min(
            (value for value in (query.end_date, query.as_of_date) if value is not None),
            default=None,
        )
        if query.start_date is not None and end_date is not None and query.start_date > end_date:
            return DigitalOracleMacroRatesProviderResult(provider="fred")
        series_ids = (query.series_ids or ("FEDFUNDS",))[: query.item_limit]
        per_series_limit, remainder = divmod(query.item_limit, len(series_ids))
        for index, series_id in enumerate(series_ids):
            limit = per_series_limit + (index < remainder)
            params: dict[str, object] = {"series_id": series_id, "file_type": "json"}
            if query.as_of_date is not None:
                # Observation dates identify periods; real-time dates bound known revisions.
                params["realtime_start"] = query.as_of_date.isoformat()
                params["realtime_end"] = query.as_of_date.isoformat()
            metadata = self._http_client.get_json(
                _FRED_SERIES_URL,
                params=params,
                timeout=query.timeout_seconds,
                provider=self.source,
                api_key=query.fred_api_key,
            )
            defaults = _fred_row_defaults(metadata, series_id)
            payload = self._http_client.get_json(
                _FRED_URL,
                params={
                    **params,
                    "observation_start": query.start_date.isoformat() if query.start_date else None,
                    "observation_end": end_date.isoformat() if end_date else None,
                    "sort_order": "desc",
                    "limit": limit,
                    "units": "lin",
                },
                timeout=query.timeout_seconds,
                provider=self.source,
                api_key=query.fred_api_key,
            )
            series_rows = map_rows(row_values(payload), defaults=defaults, warnings=warnings)
            series_rows = sorted(
                (
                    row
                    for row in series_rows
                    if (query.start_date is None or row.date >= query.start_date)
                    and (end_date is None or row.date <= end_date)
                ),
                key=lambda row: row.date,
                reverse=True,
            )
            rows.extend(series_rows[:limit])
        return DigitalOracleMacroRatesProviderResult(
            provider="fred",
            series=tuple(rows),
            warnings=tuple(warnings),
        )


def _fred_row_defaults(payload: object, series_id: str) -> MacroRatesRowDefaults:
    metadata = payload.get("seriess") if isinstance(payload, Mapping) else None
    row = metadata[0] if isinstance(metadata, list) and metadata else None
    if (
        not isinstance(row, Mapping)
        or row.get("id") != series_id
        or not isinstance(title := row.get("title"), str)
        or not title.strip()
        or not isinstance(unit := row.get("units"), str)
        or not unit.strip()
    ):
        raise DigitalOracleProviderError("fred returned malformed series metadata")
    return MacroRatesRowDefaults(
        provider="fred",
        family="macro_indicators",
        series_id=series_id,
        label=title.strip(),
        country="US",
        currency=None,
        unit=unit.strip(),
        source_url=f"https://fred.stlouisfed.org/series/{series_id}",
    )


class TreasuryMacroRatesProvider:
    source: MacroRatesSource = "treasury"

    def __init__(self, http_client: MacroRatesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxMacroRatesJsonClient()

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        if query.families and "macro_indicators" not in query.families:
            return DigitalOracleMacroRatesProviderResult(provider="treasury")
        series_ids = _treasury_series_ids(query.series_ids)
        if query.series_ids and not series_ids:
            return DigitalOracleMacroRatesProviderResult(provider="treasury")
        end_date = min(
            (value for value in (query.end_date, query.as_of_date) if value is not None),
            default=None,
        )
        if query.start_date is not None and end_date is not None and query.start_date > end_date:
            return DigitalOracleMacroRatesProviderResult(provider="treasury")
        filters = []
        if query.start_date is not None:
            filters.append(f"record_date:gte:{query.start_date.isoformat()}")
        if end_date is not None:
            filters.append(f"record_date:lte:{end_date.isoformat()}")
        warnings: list[RuntimeToolWarning] = []
        defaults = MacroRatesRowDefaults(
            provider="treasury",
            family="macro_indicators",
            series_id="UST-AVG-INTEREST",
            label="Average interest rate on US Treasury securities",
            country="US",
            currency="USD",
            unit="percent",
            source_url=_TREASURY_URL,
        )
        rows = []
        page_size = _TREASURY_FILTER_PAGE_SIZE if series_ids else query.item_limit
        max_pages = _TREASURY_FILTER_MAX_PAGES if series_ids else 1
        deadline = monotonic() + query.timeout_seconds
        for page in range(1, max_pages + 1):
            remaining = deadline - monotonic()
            if remaining <= 0:
                warnings.append(
                    runtime_warning(
                        code="macro_rates_treasury_search_truncated",
                        message=(
                            "Treasury series lookup exhausted its request time budget; "
                            "use a narrower date range to check additional observations."
                        ),
                        details={"operation": "macro_rates", "provider": "treasury"},
                    )
                )
                break
            payload = self._http_client.get_json(
                _TREASURY_URL,
                params={
                    "page[size]": page_size,
                    "page[number]": page,
                    "sort": "-record_date",
                    "filter": ",".join(filters) or None,
                },
                timeout=remaining,
                provider=self.source,
            )
            page_rows = row_values(payload)
            rows.extend(
                row
                for row in map_rows(
                    _treasury_rows(page_rows, warnings=warnings),
                    defaults=defaults,
                    warnings=warnings,
                )
                if (not series_ids or row.series_id.casefold() in series_ids)
                and (query.start_date is None or row.date >= query.start_date)
                and (end_date is None or row.date <= end_date)
            )
            if len(rows) >= query.item_limit or len(page_rows) < page_size:
                break
        else:
            if series_ids:
                warnings.append(
                    runtime_warning(
                        code="macro_rates_treasury_search_truncated",
                        message=(
                            "Treasury series lookup reached its bounded search window; "
                            "use a narrower date range to check additional observations."
                        ),
                        details={"operation": "macro_rates", "provider": "treasury"},
                    )
                )
        rows = sorted(
            rows,
            key=lambda row: (row.date, row.series_id),
            reverse=True,
        )
        if query.as_of_date is not None:
            warnings.append(
                runtime_warning(
                    code="macro_rates_vintage_unavailable",
                    message=(
                        "Treasury average interest rates are filtered by record date; "
                        "historical publication times and revisions are unavailable."
                    ),
                    details={"operation": "macro_rates", "provider": "treasury"},
                )
            )
        return DigitalOracleMacroRatesProviderResult(
            provider="treasury",
            series=tuple(rows[: query.item_limit]),
            warnings=tuple(warnings),
        )


def _treasury_series_ids(series_ids: tuple[str, ...] | None) -> set[str]:
    requested = set()
    for series_id in series_ids or ():
        parts = series_id.split(":")
        if len(parts) != 3 or parts[0].casefold() != "ust-avg-interest":
            continue
        try:
            names = [unquote(part, errors="strict") for part in parts[1:]]
        except UnicodeDecodeError:
            continue
        if all(
            name.strip() and quote(name, safe="").casefold() == part.casefold()
            for name, part in zip(names, parts[1:], strict=True)
        ):
            requested.add(series_id.casefold())
    return requested


def _treasury_rows(payload: object, *, warnings: list[RuntimeToolWarning]) -> list[object]:
    rows: list[object] = []
    for row in row_values(payload):
        if isinstance(row, Mapping):
            security_type = row.get("security_type_desc")
            security = row.get("security_desc")
            if (
                isinstance(security_type, str)
                and security_type.strip()
                and isinstance(security, str)
                and security.strip()
            ):
                security_type, security = security_type.strip(), security.strip()
                rows.append(
                    {
                        "date": row.get("record_date"),
                        "value": row.get("avg_interest_rate_amt"),
                        "series_id": (
                            f"UST-AVG-INTEREST:{quote(security_type, safe='')}:"
                            f"{quote(security, safe='')}"
                        ),
                        "label": f"Average interest rate: {security_type} / {security}",
                    }
                )
                continue
        warnings.append(
            runtime_warning(
                code="macro_rates_malformed_payload",
                message="Treasury returned an average-interest-rate row without security identity.",
                details={
                    "operation": "macro_rates",
                    "provider": "treasury",
                    "field": "row",
                },
            )
        )
    return rows


class BisMacroRatesProvider:
    source: MacroRatesSource = "bis"

    def __init__(self, http_client: MacroRatesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxMacroRatesJsonClient()

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        payload = self._http_client.get_json(
            _BIS_URL,
            params={},
            timeout=query.timeout_seconds,
            provider=self.source,
        )
        warnings: list[RuntimeToolWarning] = []
        return DigitalOracleMacroRatesProviderResult(
            provider="bis",
            series=tuple(
                map_rows(
                    row_values(payload),
                    defaults=MacroRatesRowDefaults(
                        provider="bis",
                        family="policy_rates",
                        series_id="BIS-POLICY-RATE",
                        label="BIS policy rate",
                        country=None,
                        currency=None,
                        unit="percent",
                        source_url="https://www.bis.org/statistics/",
                    ),
                    warnings=warnings,
                )[: query.item_limit]
            ),
            warnings=tuple(warnings),
        )


class WorldBankMacroRatesProvider:
    source: MacroRatesSource = "worldbank"

    def __init__(self, http_client: MacroRatesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxMacroRatesJsonClient()

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        payload = self._http_client.get_json(
            _WORLDBANK_URL,
            params={"format": "json", "per_page": query.item_limit},
            timeout=query.timeout_seconds,
            provider=self.source,
        )
        warnings: list[RuntimeToolWarning] = []
        return DigitalOracleMacroRatesProviderResult(
            provider="worldbank",
            series=tuple(
                map_rows(
                    row_values(payload),
                    defaults=MacroRatesRowDefaults(
                        provider="worldbank",
                        family="macro_indicators",
                        series_id="NY.GDP.MKTP.KD.ZG",
                        label="GDP growth",
                        country=None,
                        currency=None,
                        unit="percent",
                        source_url="https://data.worldbank.org/",
                    ),
                    warnings=warnings,
                )[: query.item_limit]
            ),
            warnings=tuple(warnings),
        )


class CmeFedWatchMacroRatesProvider:
    source: MacroRatesSource = "cme_fedwatch"

    def __init__(self, http_client: MacroRatesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxMacroRatesJsonClient()

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        payload = self._http_client.get_json(
            _CME_FEDWATCH_URL,
            params={},
            timeout=query.timeout_seconds,
            provider=self.source,
        )
        warnings: list[RuntimeToolWarning] = []
        return DigitalOracleMacroRatesProviderResult(
            provider="cme_fedwatch",
            series=tuple(
                map_rows(
                    row_values(payload),
                    defaults=MacroRatesRowDefaults(
                        provider="cme_fedwatch",
                        family="fedwatch",
                        series_id="CME-FEDWATCH",
                        label="CME FedWatch implied rate",
                        country="US",
                        currency="USD",
                        unit="probability",
                        source_url="https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
                    ),
                    warnings=warnings,
                )[: query.item_limit]
            ),
            warnings=tuple(warnings),
        )


def create_macro_rates_providers() -> tuple[DigitalOracleMacroRatesProvider, ...]:
    return (
        TreasuryMacroRatesProvider(),
        BisMacroRatesProvider(),
        WorldBankMacroRatesProvider(),
        CmeFedWatchMacroRatesProvider(),
        FredMacroRatesProvider(),
    )


__all__ = [
    "BisMacroRatesProvider",
    "CmeFedWatchMacroRatesProvider",
    "FredMacroRatesProvider",
    "TreasuryMacroRatesProvider",
    "WorldBankMacroRatesProvider",
    "create_macro_rates_providers",
]
