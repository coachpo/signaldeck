from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

from oracle_plugin.config import CftcPositioningReportType
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.types import (
    DigitalOracleCftcPositioningReport,
    DigitalOracleCftcPositioningRow,
    DigitalOracleProviderError,
)
from oracle_plugin.warnings import runtime_warning


@dataclass(frozen=True, slots=True)
class CftcMappedRows:
    reports: tuple[DigitalOracleCftcPositioningReport, ...]
    stale_report_dates: tuple[date, ...]


def row_values(payload: object) -> list[object]:
    if isinstance(payload, list):
        return list(cast(list[object], payload))
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError("CFTC returned malformed positioning data")
    mapping = cast(Mapping[str, object], payload)
    for key in ("data", "rows", "results"):
        value = mapping.get(key)
        if isinstance(value, list):
            return list(cast(list[object], value))
    return [mapping]


def map_rows(
    rows: Sequence[object],
    *,
    provider: str,
    report_type: CftcPositioningReportType,
    warnings: list[RuntimeToolWarning],
) -> CftcMappedRows:
    mapped_by_date: dict[date, list[DigitalOracleCftcPositioningRow]] = {}
    stale_report_dates: set[date] = set()
    report_dates = tuple(
        report_date
        for report_date in (_row_report_date(row) for row in rows)
        if report_date is not None
    )
    latest_report_date = max(report_dates, default=None)
    for row in rows:
        if not isinstance(row, Mapping):
            warnings.append(malformed_warning(report_type, "row"))
            continue
        report_date = _date_value(_first_value(row, _REPORT_DATE_KEYS))
        mapped_row = _map_row(cast(Mapping[str, object], row))
        if report_date is None or mapped_row is None:
            warnings.append(malformed_warning(report_type, "row"))
            continue
        if latest_report_date is not None and report_date < latest_report_date:
            stale_report_dates.add(report_date)
        mapped_by_date.setdefault(report_date, []).append(mapped_row)
    return CftcMappedRows(
        reports=tuple(
            DigitalOracleCftcPositioningReport(
                provider=provider,
                report_type=report_type,
                report_date=report_date,
                rows=tuple(items),
            )
            for report_date, items in sorted(mapped_by_date.items(), reverse=True)
        ),
        stale_report_dates=tuple(sorted(stale_report_dates, reverse=True)),
    )


def malformed_warning(
    report_type: CftcPositioningReportType,
    field: str,
) -> RuntimeToolWarning:
    return runtime_warning(
        code="cftc_positioning_malformed_payload",
        message=f"CFTC returned malformed {report_type} positioning {field}.",
        details={
            "operation": "cftc_positioning",
            "provider": "cftc",
            "report_type": report_type,
            "field": field,
        },
    )


def stale_dataset_warning(
    report_type: CftcPositioningReportType,
    report_dates: Sequence[date],
) -> RuntimeToolWarning:
    return runtime_warning(
        code="cftc_positioning_stale_dataset",
        message=f"CFTC returned stale {report_type} positioning report dates.",
        details={
            "operation": "cftc_positioning",
            "provider": "cftc",
            "report_type": report_type,
            "report_dates": ",".join(report_date.isoformat() for report_date in report_dates),
        },
    )


_REPORT_DATE_KEYS = (
    "report_date_as_yyyy_mm_dd",
    "report_date",
    "as_of_date",
    "asOfDate",
)


def _map_row(row: Mapping[str, object]) -> DigitalOracleCftcPositioningRow | None:
    market = _text(_first_value(row, ("market_and_exchange_names", "market_name", "market")))
    if market is None:
        return None
    non_commercial_long = _decimal(_first_value(row, ("noncomm_positions_long_all",)))
    non_commercial_short = _decimal(_first_value(row, ("noncomm_positions_short_all",)))
    commercial_long = _decimal(_first_value(row, ("comm_positions_long_all",)))
    commercial_short = _decimal(_first_value(row, ("comm_positions_short_all",)))
    producer_long = _decimal(_first_value(row, ("prod_merc_positions_long",)))
    producer_short = _decimal(_first_value(row, ("prod_merc_positions_short",)))
    swap_long = _decimal(_first_value(row, ("swap_positions_long_all",)))
    swap_short = _decimal(
        _first_value(row, ("swap__positions_short_all", "swap_positions_short_all"))
    )
    managed_long = _decimal(_first_value(row, ("m_money_positions_long_all",)))
    managed_short = _decimal(_first_value(row, ("m_money_positions_short_all",)))
    other_long = _decimal(_first_value(row, ("other_rept_positions_long_all",)))
    other_short = _decimal(_first_value(row, ("other_rept_positions_short_all",)))
    return DigitalOracleCftcPositioningRow(
        market=market,
        contract_market_code=_text(_first_value(row, ("cftc_contract_market_code", "market_code"))),
        non_commercial_long=non_commercial_long,
        non_commercial_short=non_commercial_short,
        non_commercial_spreading=_decimal(_first_value(row, ("noncomm_positions_spread_all",))),
        non_commercial_net=_net(non_commercial_long, non_commercial_short),
        commercial_long=commercial_long,
        commercial_short=commercial_short,
        commercial_net=_net(commercial_long, commercial_short),
        producer_long=producer_long,
        producer_short=producer_short,
        producer_net=_net(producer_long, producer_short),
        swap_dealer_long=swap_long,
        swap_dealer_short=swap_short,
        swap_dealer_net=_net(swap_long, swap_short),
        managed_money_long=managed_long,
        managed_money_short=managed_short,
        managed_money_spreading=_decimal(_first_value(row, ("m_money_positions_spread",))),
        managed_money_net=_net(managed_long, managed_short),
        other_reportable_long=other_long,
        other_reportable_short=other_short,
        other_reportable_spreading=_decimal(_first_value(row, ("other_rept_positions_spread",))),
        other_reportable_net=_net(other_long, other_short),
        open_interest=_decimal(_first_value(row, ("open_interest_all", "open_interest"))),
    )


def _row_report_date(row: object) -> date | None:
    if not isinstance(row, Mapping):
        return None
    return _date_value(_first_value(cast(Mapping[str, object], row), _REPORT_DATE_KEYS))


def _first_value(row: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _date_value(value: object) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _net(long_value: Decimal | None, short_value: Decimal | None) -> Decimal | None:
    if long_value is None or short_value is None:
        return None
    return long_value - short_value


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


__all__ = ["CftcMappedRows", "malformed_warning", "map_rows", "row_values", "stale_dataset_warning"]
