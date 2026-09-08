from __future__ import annotations

from oracle_plugin.config import MacroRatesSource
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.runtime_macro_rates_client import HttpxMacroRatesJsonClient, MacroRatesJsonClient
from oracle_plugin.runtime_macro_rates_payloads import MacroRatesRowDefaults, map_rows, row_values
from oracle_plugin.types import (
    DigitalOracleMacroRatesProvider,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
)

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
        for series_id in (query.series_ids or ("FEDFUNDS",))[: query.item_limit]:
            payload = self._http_client.get_json(
                _FRED_URL,
                params={"series_id": series_id, "file_type": "json"},
                timeout=query.timeout_seconds,
                provider=self.source,
                api_key=query.fred_api_key,
            )
            rows.extend(
                map_rows(
                    row_values(payload),
                    defaults=MacroRatesRowDefaults(
                        provider="fred",
                        family="macro_indicators",
                        series_id=series_id,
                        label=series_id,
                        country="US",
                        currency="USD",
                        unit="percent",
                        source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    ),
                    warnings=warnings,
                )
            )
        return DigitalOracleMacroRatesProviderResult(
            provider="fred",
            series=tuple(rows[: query.item_limit]),
            warnings=tuple(warnings),
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
