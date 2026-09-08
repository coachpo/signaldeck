from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import httpx
from oracle_plugin.config import CryptoDerivativesVenue
from oracle_plugin.types import DigitalOracleProviderError

_USER_AGENT = "signaldeck-backend/0.1"

type QueryParamValue = str | int | float | bool


class CryptoDerivativesJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: CryptoDerivativesVenue,
    ) -> object: ...


class HttpxCryptoDerivativesJsonClient:
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        provider: CryptoDerivativesVenue,
    ) -> object:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    url,
                    params=_compact_params(params),
                    headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
                )
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                f"{provider} timed out while fetching crypto derivatives",
                code="provider_timeout",
                details={"provider": provider},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc, provider=provider) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                f"{provider} is unavailable for crypto derivatives",
                code="provider_unavailable",
                details={"provider": provider},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                f"{provider} returned malformed crypto-derivatives data",
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
    provider: CryptoDerivativesVenue,
) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            f"{provider} rate limited crypto derivatives",
            code="provider_rate_limited",
            details={"provider": provider, "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        f"{provider} failed while fetching crypto derivatives",
        code="provider_unavailable" if status_code >= 500 else "provider_error",
        details={"provider": provider, "status": str(status_code)},
    )


__all__ = ["CryptoDerivativesJsonClient", "HttpxCryptoDerivativesJsonClient"]
