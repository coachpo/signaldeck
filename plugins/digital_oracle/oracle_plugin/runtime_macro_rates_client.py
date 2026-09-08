from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import httpx
from oracle_plugin.config import MacroRatesSource
from oracle_plugin.types import DigitalOracleProviderError

_USER_AGENT = "signaldeck-backend/0.1"

type QueryParamValue = str | int | float | bool


class MacroRatesJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: MacroRatesSource,
        api_key: str | None = None,
    ) -> object: ...


class HttpxMacroRatesJsonClient:
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: MacroRatesSource,
        api_key: str | None = None,
    ) -> object:
        request_params = _compact_params(params)
        if api_key is not None:
            request_params["api_key"] = api_key
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    url,
                    params=request_params,
                    headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
                )
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                f"{provider} timed out while fetching macro rates",
                code="provider_timeout",
                details={"provider": provider},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc, provider=provider) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                f"{provider} is unavailable for macro rates",
                code="provider_unavailable",
                details={"provider": provider},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                f"{provider} returned malformed macro-rates data",
                details={"provider": provider},
            ) from exc


def _compact_params(params: Mapping[str, object]) -> dict[str, QueryParamValue]:
    compact: dict[str, QueryParamValue] = {}
    for key, value in params.items():
        if isinstance(value, str | int | float | bool):
            compact[key] = value
    return compact


def _http_status_provider_error(
    exc: httpx.HTTPStatusError,
    *,
    provider: MacroRatesSource,
) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            f"{provider} rate limited macro rates",
            code="provider_rate_limited",
            details={"provider": provider, "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        f"{provider} failed while fetching macro rates",
        code="provider_unavailable" if status_code >= 500 else "provider_error",
        details={"provider": provider, "status": str(status_code)},
    )


__all__ = ["HttpxMacroRatesJsonClient", "MacroRatesJsonClient"]
