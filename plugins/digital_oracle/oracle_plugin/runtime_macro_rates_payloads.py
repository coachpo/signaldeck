from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

from oracle_plugin.config import MacroRatesFamily, MacroRatesSource
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.types import DigitalOracleMacroRatesSeries, DigitalOracleProviderError
from oracle_plugin.warnings import runtime_warning


@dataclass(frozen=True, slots=True)
class MacroRatesRowDefaults:
    provider: MacroRatesSource
    family: MacroRatesFamily
    series_id: str
    label: str
    country: str | None
    currency: str | None
    unit: str
    source_url: str


def row_values(payload: object) -> list[object]:
    if isinstance(payload, list):
        return list(cast(list[object], payload))
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError("macro rates provider returned malformed data")
    mapping = cast(Mapping[str, object], payload)
    for key in ("observations", "data", "values", "rows"):
        value = mapping.get(key)
        if isinstance(value, list):
            return list(cast(list[object], value))
    return [mapping]


def map_rows(
    rows: Sequence[object],
    *,
    defaults: MacroRatesRowDefaults,
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleMacroRatesSeries]:
    mapped: list[DigitalOracleMacroRatesSeries] = []
    for row in rows:
        if not isinstance(row, Mapping):
            warnings.append(_malformed_warning(defaults.provider, "row"))
            continue
        item = _map_row(cast(Mapping[str, object], row), defaults=defaults)
        if item is None:
            warnings.append(_malformed_warning(defaults.provider, "row"))
            continue
        mapped.append(item)
    return mapped


def _map_row(
    row: Mapping[str, object],
    *,
    defaults: MacroRatesRowDefaults,
) -> DigitalOracleMacroRatesSeries | None:
    point_date = _date_value(_first_value(row, ("date", "record_date", "time", "TIME_PERIOD")))
    point_value = _decimal_value(
        _first_value(row, ("value", "avg_interest_rate_amt", "obs_value", "OBS_VALUE"))
    )
    if point_date is None or point_value is None:
        return None
    tenor = _normalize_tenor(_text(_first_value(row, ("tenor", "security_term", "maturity"))))
    return DigitalOracleMacroRatesSeries(
        provider=defaults.provider,
        family=defaults.family,
        series_id=_text(_first_value(row, ("series_id", "seriesId", "id", "indicator")))
        or _series_id(defaults.series_id, tenor),
        label=_text(_first_value(row, ("label", "name", "security_desc", "indicatorName")))
        or defaults.label,
        country=_text(_first_value(row, ("country", "countryiso3code", "ref_area")))
        or defaults.country,
        currency=_text(_first_value(row, ("currency", "currency_code"))) or defaults.currency,
        unit=_text(_first_value(row, ("unit", "unit_measure"))) or defaults.unit,
        date=point_date,
        value=point_value,
        tenor=tenor,
        source_url=_text(_first_value(row, ("source_url", "sourceUrl"))) or defaults.source_url,
    )


def _series_id(default_series_id: str, tenor: str | None) -> str:
    if tenor is None:
        return default_series_id
    return f"UST-{tenor}" if default_series_id == "UST-YIELD" else f"{default_series_id}-{tenor}"


def _first_value(row: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


def _date_value(value: object) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text == ".":
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_tenor(value: str | None) -> str | None:
    if value is None:
        return None
    compact = value.upper().replace(" ", "")
    return compact.replace("YR", "Y").replace("YEAR", "Y").replace("MONTH", "M")


def _malformed_warning(provider: MacroRatesSource, field: str) -> RuntimeToolWarning:
    return runtime_warning(
        code="macro_rates_malformed_payload",
        message=f"{provider} returned malformed macro-rates {field}.",
        details={"operation": "macro_rates", "provider": provider, "field": field},
    )


__all__ = ["MacroRatesRowDefaults", "map_rows", "row_values"]
