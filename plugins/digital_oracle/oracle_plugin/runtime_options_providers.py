from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

import yfinance as yf
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.runtime_options_payloads import (
    map_option_rows,
    rows_from_table,
    spot_unavailable_warning,
)
from oracle_plugin.types import (
    DigitalOracleOptionsChain,
    DigitalOracleOptionsProvider,
    DigitalOracleOptionsProviderQuery,
    DigitalOracleOptionsProviderResult,
    DigitalOracleProviderError,
)


class OptionsTable(Protocol):
    def to_dict(self, orient: str) -> list[Mapping[str, object]]: ...


class OptionsChainPayload(Protocol):
    @property
    def calls(self) -> OptionsTable: ...

    @property
    def puts(self) -> OptionsTable: ...


class OptionsTicker(Protocol):
    @property
    def options(self) -> Sequence[str]: ...

    @property
    def fast_info(self) -> Mapping[str, object]: ...

    @property
    def info(self) -> Mapping[str, object]: ...

    def option_chain(self, date: str) -> OptionsChainPayload: ...


class OptionsTickerFactory(Protocol):
    def __call__(self, symbol: str) -> OptionsTicker: ...


class YahooOptionsProvider:
    provider_name = "yahoo"

    def __init__(self, ticker_factory: OptionsTickerFactory = yf.Ticker) -> None:
        self._ticker_factory = ticker_factory

    def lookup_options(
        self,
        query: DigitalOracleOptionsProviderQuery,
    ) -> DigitalOracleOptionsProviderResult:
        ticker = self._ticker_factory(query.symbol)
        expirations = _selected_expirations(ticker.options, query.expirations)
        spot_price = _spot_price(ticker)
        warnings: list[RuntimeToolWarning] = []
        if query.moneyness != "all" and spot_price is None:
            warnings.append(spot_unavailable_warning(query.symbol, self.provider_name))
        chains: list[DigitalOracleOptionsChain] = []
        for expiration in expirations:
            chain_payload = ticker.option_chain(expiration)
            rows = map_option_rows(
                calls=rows_from_table(
                    chain_payload.calls,
                    provider=self.provider_name,
                    side="call",
                ),
                puts=rows_from_table(chain_payload.puts, provider=self.provider_name, side="put"),
                include_greeks=query.include_greeks,
                item_limit=query.item_limit,
                moneyness=query.moneyness,
                spot_price=spot_price,
            )
            chains.append(
                DigitalOracleOptionsChain(
                    provider=self.provider_name,
                    symbol=query.symbol,
                    expiry_date=_expiration_date(expiration),
                    calls=rows.calls,
                    puts=rows.puts,
                )
            )
        return DigitalOracleOptionsProviderResult(
            provider=self.provider_name,
            chains=tuple(chains),
            warnings=tuple(warnings),
        )


def create_options_providers() -> tuple[DigitalOracleOptionsProvider, ...]:
    return (YahooOptionsProvider(),)


def _selected_expirations(
    available_expirations: Sequence[str],
    requested_expirations: tuple[date, ...] | None,
) -> tuple[str, ...]:
    available = tuple(str(expiration) for expiration in available_expirations)
    if requested_expirations is None:
        return available
    requested = {expiration.isoformat() for expiration in requested_expirations}
    return tuple(expiration for expiration in available if expiration in requested)


def _expiration_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DigitalOracleProviderError(
            "Yahoo returned malformed option expiration data",
            details={"provider": "yahoo", "field": "expiration"},
        ) from exc


def _spot_price(ticker: OptionsTicker) -> Decimal | None:
    for row in (ticker.fast_info, ticker.info):
        value = _first_value(row, ("last_price", "lastPrice", "regularMarketPrice", "currentPrice"))
        price = _decimal(value)
        if price is not None:
            return price
    return None


def _first_value(row: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


__all__ = [
    "OptionsChainPayload",
    "OptionsTable",
    "OptionsTicker",
    "YahooOptionsProvider",
    "create_options_providers",
]
