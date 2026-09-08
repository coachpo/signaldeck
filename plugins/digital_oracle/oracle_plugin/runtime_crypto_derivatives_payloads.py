from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.types import (
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
    DigitalOracleProviderError,
)
from oracle_plugin.warnings import runtime_warning


def object_payload(payload: object, *, provider: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError(
            f"{provider} returned malformed crypto-derivatives data",
            details={"provider": provider},
        )
    return cast(Mapping[str, object], payload)


def result_rows(payload: object, *, provider: str) -> list[object]:
    mapping = object_payload(payload, provider=provider)
    value = mapping.get("result")
    if isinstance(value, list):
        return list(cast(list[object], value))
    if isinstance(value, Mapping):
        return [value]
    return [mapping]


def map_coingecko_spot(
    payload: object,
    *,
    assets: Sequence[str],
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleCryptoDerivativesSpotQuote]:
    mapping = object_payload(payload, provider="coingecko")
    quotes: list[DigitalOracleCryptoDerivativesSpotQuote] = []
    for asset in assets:
        coin_id = coingecko_coin_id(asset)
        row = mapping.get(coin_id)
        if not isinstance(row, Mapping):
            warnings.append(malformed_warning("coingecko", "spot row", asset))
            continue
        quote = _coingecko_quote(asset, cast(Mapping[str, object], row))
        if quote is None:
            warnings.append(malformed_warning("coingecko", "spot row", asset))
            continue
        quotes.append(quote)
    return quotes


def map_coingecko_global(payload: object) -> DigitalOracleCryptoDerivativesGlobalMetrics | None:
    mapping = object_payload(payload, provider="coingecko")
    data = mapping.get("data") if isinstance(mapping.get("data"), Mapping) else mapping
    row = cast(Mapping[str, object], data)
    market_caps = row.get("total_market_cap")
    volumes = row.get("total_volume")
    return DigitalOracleCryptoDerivativesGlobalMetrics(
        provider="coingecko",
        symbol=None,
        market_cap=_nested_decimal(market_caps, "usd"),
        volume_24h=_nested_decimal(volumes, "usd"),
        as_of=_timestamp(row.get("updated_at")),
    )


def map_deribit_instruments(
    payload: object,
    *,
    asset: str,
    expirations: tuple[date, ...] | None,
    item_limit: int,
    warnings: list[RuntimeToolWarning],
) -> tuple[
    tuple[DigitalOracleCryptoDerivativesTermPoint, ...],
    tuple[DigitalOracleCryptoDerivativesOptionSummary, ...],
]:
    term_points: list[DigitalOracleCryptoDerivativesTermPoint] = []
    options: list[DigitalOracleCryptoDerivativesOptionSummary] = []
    allowed_expirations = set(expirations or ())
    for row in result_rows(payload, provider="deribit"):
        if not isinstance(row, Mapping):
            warnings.append(malformed_warning("deribit", "instrument row", asset))
            continue
        item = cast(Mapping[str, object], row)
        expiry_date = _expiry_date(item.get("expiration_timestamp"))
        instrument = _text(item.get("instrument_name"))
        if expiry_date is None or instrument is None:
            warnings.append(malformed_warning("deribit", "instrument row", asset))
            continue
        if allowed_expirations and expiry_date not in allowed_expirations:
            continue
        strike = _decimal(item.get("strike"))
        option_type = _option_type(item.get("option_type"))
        if strike is not None and option_type is not None:
            options.append(
                DigitalOracleCryptoDerivativesOptionSummary(
                    provider="deribit",
                    symbol=asset,
                    expiry_date=expiry_date,
                    strike=strike,
                    option_type=option_type,
                )
            )
        else:
            term_points.append(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="deribit",
                    symbol=asset,
                    expiry_date=expiry_date,
                    instrument=instrument,
                )
            )
    return tuple(term_points[:item_limit]), tuple(options[:item_limit])


def map_deribit_summary(
    payload: object,
    *,
    term_points: Sequence[DigitalOracleCryptoDerivativesTermPoint],
    options: Sequence[DigitalOracleCryptoDerivativesOptionSummary],
) -> tuple[
    tuple[DigitalOracleCryptoDerivativesTermPoint, ...],
    tuple[DigitalOracleCryptoDerivativesOptionSummary, ...],
]:
    summary_by_instrument = _summary_by_instrument(payload)
    return (
        tuple(
            _term_with_summary(point, summary_by_instrument.get(point.instrument))
            for point in term_points
        ),
        tuple(_option_with_summary(option, summary_by_instrument) for option in options),
    )


def coingecko_coin_id(asset: str) -> str:
    normalized = asset.strip().lower()
    return {"btc": "bitcoin", "xbt": "bitcoin", "eth": "ethereum"}.get(normalized, normalized)


def malformed_warning(provider: str, field: str, asset: str | None = None) -> RuntimeToolWarning:
    details = {"operation": "crypto_derivatives", "provider": provider, "field": field}
    if asset is not None:
        details["asset"] = asset
    return runtime_warning(
        code="crypto_derivatives_malformed_payload",
        message=f"{provider} returned malformed crypto-derivatives {field}.",
        details=details,
    )


def _coingecko_quote(
    asset: str,
    row: Mapping[str, object],
) -> DigitalOracleCryptoDerivativesSpotQuote | None:
    price = _decimal(row.get("usd"))
    if price is None:
        return None
    return DigitalOracleCryptoDerivativesSpotQuote(
        provider="coingecko",
        symbol=asset,
        price=price,
        currency="USD",
        as_of=_timestamp(row.get("last_updated_at")),
    )


def _term_with_summary(
    point: DigitalOracleCryptoDerivativesTermPoint,
    summary: Mapping[str, object] | None,
) -> DigitalOracleCryptoDerivativesTermPoint:
    return DigitalOracleCryptoDerivativesTermPoint(
        provider=point.provider,
        symbol=point.symbol,
        expiry_date=point.expiry_date,
        instrument=point.instrument,
        implied_volatility=_decimal(summary.get("mark_iv")) if summary is not None else None,
        open_interest=_decimal(summary.get("open_interest")) if summary is not None else None,
    )


def _option_with_summary(
    option: DigitalOracleCryptoDerivativesOptionSummary,
    summary_by_instrument: Mapping[str | None, Mapping[str, object]],
) -> DigitalOracleCryptoDerivativesOptionSummary:
    instrument_prefix = f"{option.symbol}-{option.expiry_date:%d%b%y}".upper()
    option_suffix = f"-{option.strike}-{option.option_type[0].upper()}"
    summary = next(
        (
            row
            for name, row in summary_by_instrument.items()
            if name
            and name.upper().startswith(instrument_prefix)
            and name.upper().endswith(option_suffix)
        ),
        None,
    )
    return DigitalOracleCryptoDerivativesOptionSummary(
        provider=option.provider,
        symbol=option.symbol,
        expiry_date=option.expiry_date,
        strike=option.strike,
        option_type=option.option_type,
        implied_volatility=_decimal(summary.get("mark_iv")) if summary is not None else None,
        open_interest=_decimal(summary.get("open_interest")) if summary is not None else None,
    )


def _summary_by_instrument(payload: object) -> dict[str | None, Mapping[str, object]]:
    return {
        _text(cast(Mapping[str, object], row).get("instrument_name")): cast(
            Mapping[str, object],
            row,
        )
        for row in result_rows(payload, provider="deribit")
        if isinstance(row, Mapping)
    }


def _nested_decimal(value: object, key: str) -> Decimal | None:
    if not isinstance(value, Mapping):
        return None
    return _decimal(cast(Mapping[str, object], value).get(key))


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _expiry_date(value: object) -> date | None:
    timestamp = _decimal(value)
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp) / 1000, tz=UTC).date()


def _timestamp(value: object) -> datetime | None:
    timestamp = _decimal(value)
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=UTC)


def _option_type(value: object) -> Literal["call", "put"] | None:
    text = _text(value)
    match text:
        case "call":
            return "call"
        case "put":
            return "put"
        case _:
            return None


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        return normalized or None
    return None


__all__ = [
    "coingecko_coin_id",
    "malformed_warning",
    "map_coingecko_global",
    "map_coingecko_spot",
    "map_deribit_instruments",
    "map_deribit_summary",
    "object_payload",
    "result_rows",
]
