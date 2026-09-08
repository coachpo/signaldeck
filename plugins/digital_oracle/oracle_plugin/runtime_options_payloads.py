from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from oracle_plugin.config import OptionsMoneyness
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.types import (
    DigitalOracleOptionContract,
    DigitalOracleOptionGreeks,
    DigitalOracleProviderError,
)
from oracle_plugin.warnings import runtime_warning

_NEAR_THE_MONEY_RATIO = Decimal("0.05")
OptionSide = Literal["call", "put"]


@dataclass(frozen=True, slots=True)
class OptionRows:
    calls: tuple[DigitalOracleOptionContract, ...]
    puts: tuple[DigitalOracleOptionContract, ...]


def rows_from_table(
    value: object,
    *,
    provider: str,
    side: OptionSide,
) -> Sequence[Mapping[str, object]]:
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        raise DigitalOracleProviderError(
            f"{provider} returned malformed {side} option rows",
            details={"provider": provider, "field": side},
        )
    rows = to_dict("records")
    return tuple(row for row in rows if isinstance(row, Mapping))


def map_option_rows(
    *,
    calls: Sequence[Mapping[str, object]],
    puts: Sequence[Mapping[str, object]],
    include_greeks: bool,
    item_limit: int,
    moneyness: OptionsMoneyness,
    spot_price: Decimal | None,
) -> OptionRows:
    return OptionRows(
        calls=tuple(
            _limit_contracts(
                calls,
                include_greeks=include_greeks,
                item_limit=item_limit,
                moneyness=moneyness,
                side="call",
                spot_price=spot_price,
            )
        ),
        puts=tuple(
            _limit_contracts(
                puts,
                include_greeks=include_greeks,
                item_limit=item_limit,
                moneyness=moneyness,
                side="put",
                spot_price=spot_price,
            )
        ),
    )


def spot_unavailable_warning(symbol: str, provider: str) -> RuntimeToolWarning:
    return runtime_warning(
        code="options_spot_unavailable",
        message=(
            f"{provider} did not return a spot price for {symbol}; "
            "moneyness filtering was skipped."
        ),
        details={"operation": "options", "provider": provider, "symbol": symbol},
    )


def _limit_contracts(
    rows: Sequence[Mapping[str, object]],
    *,
    include_greeks: bool,
    item_limit: int,
    moneyness: OptionsMoneyness,
    side: OptionSide,
    spot_price: Decimal | None,
) -> list[DigitalOracleOptionContract]:
    contracts: list[DigitalOracleOptionContract] = []
    for row in rows:
        contract = _map_contract(row, include_greeks=include_greeks)
        if contract is None or not _matches_moneyness(
            contract.strike,
            side=side,
            spot_price=spot_price,
            moneyness=moneyness,
        ):
            continue
        contracts.append(contract)
        if len(contracts) >= item_limit:
            break
    return contracts


def _map_contract(
    row: Mapping[str, object],
    *,
    include_greeks: bool,
) -> DigitalOracleOptionContract | None:
    contract_symbol = _text(_first_value(row, ("contractSymbol", "contract_symbol", "symbol")))
    strike = _decimal(_first_value(row, ("strike",)))
    if contract_symbol is None or strike is None:
        return None
    return DigitalOracleOptionContract(
        contract_symbol=contract_symbol,
        strike=strike,
        last_price=_decimal(_first_value(row, ("lastPrice", "last_price", "last"))),
        bid=_decimal(_first_value(row, ("bid",))),
        ask=_decimal(_first_value(row, ("ask",))),
        volume=_decimal(_first_value(row, ("volume",))),
        open_interest=_decimal(_first_value(row, ("openInterest", "open_interest"))),
        greeks=_map_greeks(row) if include_greeks else None,
    )


def _map_greeks(row: Mapping[str, object]) -> DigitalOracleOptionGreeks | None:
    greeks = DigitalOracleOptionGreeks(
        delta=_decimal(_first_value(row, ("delta",))),
        gamma=_decimal(_first_value(row, ("gamma",))),
        theta=_decimal(_first_value(row, ("theta",))),
        vega=_decimal(_first_value(row, ("vega",))),
        rho=_decimal(_first_value(row, ("rho",))),
        implied_volatility=_decimal(_first_value(row, ("impliedVolatility", "implied_volatility"))),
    )
    if any(
        value is not None
        for value in (
            greeks.delta,
            greeks.gamma,
            greeks.theta,
            greeks.vega,
            greeks.rho,
            greeks.implied_volatility,
        )
    ):
        return greeks
    return None


def _matches_moneyness(
    strike: Decimal,
    *,
    side: OptionSide,
    spot_price: Decimal | None,
    moneyness: OptionsMoneyness,
) -> bool:
    if moneyness == "all" or spot_price is None:
        return True
    if moneyness == "near_the_money":
        return abs(strike - spot_price) / spot_price <= _NEAR_THE_MONEY_RATIO
    if side == "call":
        return strike < spot_price if moneyness == "itm" else strike > spot_price
    return strike > spot_price if moneyness == "itm" else strike < spot_price


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


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        return normalized or None
    return None


__all__ = ["OptionRows", "map_option_rows", "rows_from_table", "spot_unavailable_warning"]
