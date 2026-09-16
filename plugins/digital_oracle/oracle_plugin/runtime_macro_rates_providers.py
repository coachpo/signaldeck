from __future__ import annotations

from collections.abc import Mapping

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

_FRED_SERIES_URL = "https://api.stlouisfed.org/fred/series"
_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
_TREASURY_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
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
        payload = self._http_client.get_json(
            _TREASURY_URL,
            params={"page[size]": query.item_limit},
            timeout=query.timeout_seconds,
            provider=self.source,
        )
        warnings: list[RuntimeToolWarning] = []
        return DigitalOracleMacroRatesProviderResult(
            provider="treasury",
            series=tuple(
                map_rows(
                    row_values(payload),
                    defaults=MacroRatesRowDefaults(
                        provider="treasury",
                        family="yield_curve",
                        series_id="UST-YIELD",
                        label="US Treasury yield curve",
                        country="US",
                        currency="USD",
                        unit="percent",
                        source_url="https://home.treasury.gov/",
                    ),
                    warnings=warnings,
                )[: query.item_limit]
            ),
            warnings=tuple(warnings),
        )


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
