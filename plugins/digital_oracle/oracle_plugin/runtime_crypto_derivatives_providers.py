from __future__ import annotations

from oracle_plugin.config import CryptoDerivativesVenue
from oracle_plugin.contracts import RuntimeToolWarning
from oracle_plugin.runtime_crypto_derivatives_client import (
    CryptoDerivativesJsonClient,
    HttpxCryptoDerivativesJsonClient,
)
from oracle_plugin.runtime_crypto_derivatives_orderbook import map_deribit_order_book
from oracle_plugin.runtime_crypto_derivatives_payloads import (
    coingecko_coin_id,
    malformed_warning,
    map_coingecko_global,
    map_coingecko_spot,
    map_deribit_instruments,
    map_deribit_summary,
)
from oracle_plugin.types import (
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesProvider,
    DigitalOracleCryptoDerivativesProviderQuery,
    DigitalOracleCryptoDerivativesProviderResult,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
)

_COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
_COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
_DERIBIT_INSTRUMENTS_URL = "https://www.deribit.com/api/v2/public/get_instruments"
_DERIBIT_SUMMARY_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
_DERIBIT_ORDER_BOOK_URL = "https://www.deribit.com/api/v2/public/get_order_book"


class CoinGeckoCryptoDerivativesProvider:
    venue: CryptoDerivativesVenue = "coingecko"

    def __init__(self, http_client: CryptoDerivativesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxCryptoDerivativesJsonClient()

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesProviderQuery,
    ) -> DigitalOracleCryptoDerivativesProviderResult:
        warnings: list[RuntimeToolWarning] = []
        spot: tuple[DigitalOracleCryptoDerivativesSpotQuote, ...] = ()
        global_metrics: tuple[DigitalOracleCryptoDerivativesGlobalMetrics, ...] = ()
        if "spot" in query.data_types:
            spot_payload = self._http_client.get_json(
                _COINGECKO_PRICE_URL,
                params={
                    "ids": ",".join(coingecko_coin_id(asset) for asset in query.assets),
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_last_updated_at": "true",
                },
                timeout=query.timeout_seconds,
                provider=self.venue,
            )
            spot = tuple(map_coingecko_spot(spot_payload, assets=query.assets, warnings=warnings))
        if "global_market" in query.data_types:
            global_payload = self._http_client.get_json(
                _COINGECKO_GLOBAL_URL,
                params={},
                timeout=query.timeout_seconds,
                provider=self.venue,
            )
            metrics = map_coingecko_global(global_payload)
            global_metrics = () if metrics is None else (metrics,)
        return DigitalOracleCryptoDerivativesProviderResult(
            provider="coingecko",
            spot=spot[: query.item_limit],
            global_metrics=global_metrics,
            warnings=tuple(warnings),
        )


class DeribitCryptoDerivativesProvider:
    venue: CryptoDerivativesVenue = "deribit"

    def __init__(self, http_client: CryptoDerivativesJsonClient | None = None) -> None:
        self._http_client = http_client or HttpxCryptoDerivativesJsonClient()

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesProviderQuery,
    ) -> DigitalOracleCryptoDerivativesProviderResult:
        warnings: list[RuntimeToolWarning] = []
        term_structure: list[DigitalOracleCryptoDerivativesTermPoint] = []
        options: list[DigitalOracleCryptoDerivativesOptionSummary] = []
        order_books: list[DigitalOracleCryptoDerivativesOrderBook] = []
        if _needs_deribit_instruments(query):
            for asset in query.assets:
                instrument_payload = self._http_client.get_json(
                    _DERIBIT_INSTRUMENTS_URL,
                    params={"currency": asset, "expired": "false"},
                    timeout=query.timeout_seconds,
                    provider=self.venue,
                )
                asset_terms, asset_options = map_deribit_instruments(
                    instrument_payload,
                    asset=asset,
                    expirations=query.expirations,
                    item_limit=query.item_limit,
                    warnings=warnings,
                )
                summary_payload = self._http_client.get_json(
                    _DERIBIT_SUMMARY_URL,
                    params={"currency": asset},
                    timeout=query.timeout_seconds,
                    provider=self.venue,
                )
                asset_terms, asset_options = map_deribit_summary(
                    summary_payload,
                    term_points=asset_terms,
                    options=asset_options,
                )
                term_structure.extend(asset_terms)
                options.extend(asset_options)
                if query.include_order_book:
                    instrument = _first_orderbook_instrument(asset_terms, asset_options)
                    if instrument is None:
                        warnings.append(malformed_warning("deribit", "orderbook instrument", asset))
                        continue
                    order_payload = self._http_client.get_json(
                        _DERIBIT_ORDER_BOOK_URL,
                        params={"instrument_name": instrument, "depth": query.depth_limit},
                        timeout=query.timeout_seconds,
                        provider=self.venue,
                    )
                    order_book = map_deribit_order_book(
                        order_payload,
                        asset=asset,
                        depth_limit=query.depth_limit,
                    )
                    if order_book is None:
                        warnings.append(malformed_warning("deribit", "orderbook", asset))
                    else:
                        order_books.append(order_book)
        return DigitalOracleCryptoDerivativesProviderResult(
            provider="deribit",
            term_structure=tuple(term_structure[: query.item_limit]),
            options=tuple(options[: query.item_limit]),
            order_books=tuple(order_books[: query.item_limit]),
            warnings=tuple(warnings),
        )


def create_crypto_derivatives_providers() -> tuple[DigitalOracleCryptoDerivativesProvider, ...]:
    return (DeribitCryptoDerivativesProvider(), CoinGeckoCryptoDerivativesProvider())


def _needs_deribit_instruments(query: DigitalOracleCryptoDerivativesProviderQuery) -> bool:
    return bool({"term_structure", "option_chain", "order_book"} & set(query.data_types))


def _first_orderbook_instrument(term_points: object, options: object) -> str | None:
    if isinstance(term_points, tuple) and term_points:
        return str(term_points[0].instrument)
    if isinstance(options, tuple) and options:
        option = options[0]
        return (
            f"{option.symbol}-{option.expiry_date:%d%b%y}-"
            f"{option.strike}-{option.option_type[0].upper()}"
        )
    return None


__all__ = [
    "CoinGeckoCryptoDerivativesProvider",
    "DeribitCryptoDerivativesProvider",
    "create_crypto_derivatives_providers",
]
