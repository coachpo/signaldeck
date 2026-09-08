from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

import httpx
from oracle_plugin.config import CftcPositioningReportType
from oracle_plugin.types import DigitalOracleProviderError

_USER_AGENT = "signaldeck-backend/0.1"

type QueryParamValue = str | int | float | bool


class CftcPositioningJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        report_type: CftcPositioningReportType,
    ) -> object: ...


class HttpxCftcPositioningJsonClient:
    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        timeout: float,
        report_type: CftcPositioningReportType,
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
                f"CFTC timed out while fetching {report_type} positioning data",
                code="provider_timeout",
                details={"provider": "cftc", "report_type": report_type},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc, report_type=report_type) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                f"CFTC is unavailable for {report_type} positioning data",
                code="provider_unavailable",
                details={"provider": "cftc", "report_type": report_type},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                f"CFTC returned malformed {report_type} positioning data",
                details={"provider": "cftc", "report_type": report_type},
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
    report_type: CftcPositioningReportType,
) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            f"CFTC rate limited {report_type} positioning data",
            code="provider_rate_limited",
            details={"provider": "cftc", "report_type": report_type, "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        f"CFTC failed while fetching {report_type} positioning data",
        code="provider_unavailable" if status_code >= 500 else "provider_error",
        details={"provider": "cftc", "report_type": report_type, "status": str(status_code)},
    )


__all__ = ["CftcPositioningJsonClient", "HttpxCftcPositioningJsonClient"]
