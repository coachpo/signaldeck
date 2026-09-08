from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import cast

from oracle_plugin.types import (
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesOrderBookLevel,
)


def map_deribit_order_book(
    payload: object,
    *,
    asset: str,
    depth_limit: int,
) -> DigitalOracleCryptoDerivativesOrderBook | None:
    if not isinstance(payload, Mapping):
        return None
    row = cast(Mapping[str, object], payload)
    data = row.get("result") if isinstance(row.get("result"), Mapping) else row
    mapping = cast(Mapping[str, object], data)
    instrument = _text(mapping.get("instrument_name"))
    bids = _levels(mapping.get("bids"), depth_limit=depth_limit)
    asks = _levels(mapping.get("asks"), depth_limit=depth_limit)
    if instrument is None or (not bids and not asks):
        return None
    return DigitalOracleCryptoDerivativesOrderBook(
        provider="deribit",
        symbol=asset,
        instrument=instrument,
        bids=tuple(bids),
        asks=tuple(asks),
        depth_limit=depth_limit,
    )


def _levels(
    value: object,
    *,
    depth_limit: int,
) -> list[DigitalOracleCryptoDerivativesOrderBookLevel]:
    if not isinstance(value, list):
        return []
    levels: list[DigitalOracleCryptoDerivativesOrderBookLevel] = []
    for raw_level in cast(list[object], value)[:depth_limit]:
        if not isinstance(raw_level, list | tuple) or len(raw_level) < 2:
            continue
        price = _decimal(raw_level[0])
        size = _decimal(raw_level[1])
        if price is not None and size is not None:
            levels.append(DigitalOracleCryptoDerivativesOrderBookLevel(price=price, size=size))
    return levels


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        return normalized or None
    return None


__all__ = ["map_deribit_order_book"]
