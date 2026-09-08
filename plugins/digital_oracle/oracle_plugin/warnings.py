from __future__ import annotations

import re
from collections.abc import Mapping

from oracle_plugin.contracts import RuntimeToolWarning
from plugin_runtime.common import to_camel

from .factory import DigitalOracleProviderFailure
from .types import DigitalOracleProviderError

_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_ -]?key|token|secret|password|credential)(\s*[=:]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9][A-Za-z0-9_-]*")
_SENSITIVE_WARNING_DETAIL_KEY_RE = re.compile(
    r"api[_-]?key|authorization|bearer|credential|password|secret|token",
    re.IGNORECASE,
)
_WARNING_DETAIL_KEY_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")

_PROVIDER_WARNING_CODE_BY_ERROR_CODE = {
    "provider_timeout": "{operation}_provider_timeout",
    "provider_rate_limited": "{operation}_provider_rate_limited",
    "provider_unavailable": "{operation}_provider_unavailable",
    "provider_api_key_missing": "{operation}_api_key_missing",
}


def warning_from_provider_failure(
    failure: DigitalOracleProviderFailure,
    *,
    operation: str,
) -> RuntimeToolWarning:
    return runtime_warning(
        code=failure.code,
        message=failure.message,
        details={"operation": operation, **dict(failure.details)},
    )


def warning_from_provider_error(
    exc: DigitalOracleProviderError,
    *,
    operation: str,
    provider: str,
) -> RuntimeToolWarning:
    template = _PROVIDER_WARNING_CODE_BY_ERROR_CODE.get(exc.code, "{operation}_provider_error")
    return runtime_warning(
        code=template.format(operation=operation),
        message=str(exc) or f"{provider} provider failed.",
        details={"operation": operation, "provider": provider, **dict(exc.details)},
    )


def warning_from_unhandled_provider_error(
    exc: Exception,
    *,
    operation: str,
    provider: str,
) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_provider_error",
        message=str(exc) or f"{provider} provider failed.",
        details={"operation": operation, "provider": provider},
    )


def provider_unavailable_warning(*, operation: str, provider: str) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_provider_unavailable",
        message=f"No {provider} provider is configured for {operation}.",
        details={"operation": operation, "provider": provider},
    )


def empty_result_warning(*, operation: str, provider: str) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_empty",
        message=f"No {operation} data returned from {provider}.",
        details={"operation": operation, "provider": provider},
    )


def partial_result_warning(
    *,
    operation: str,
    requested_providers: tuple[str, ...],
    uncovered_providers: tuple[str, ...],
) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_partial_result",
        message=f"{operation} coverage is partial for the requested providers.",
        details={
            "operation": operation,
            "providers": ",".join(requested_providers),
            "uncovered_providers": ",".join(uncovered_providers),
        },
    )


def truncated_result_warning(*, operation: str, limit: int) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_truncated",
        message=f"{operation} results were truncated to {limit} items.",
        details={"operation": operation, "limit": str(limit)},
    )


def unavailable_result_warning(*, operation: str) -> RuntimeToolWarning:
    return runtime_warning(
        code=f"{operation}_unavailable",
        message=f"No {operation} data available from configured providers.",
        details={"operation": operation},
    )


def runtime_warning(
    *,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code=code,
        message=_public_warning_message(message),
        details=_public_warning_details(details or {}),
    )


def _public_warning_message(message: str) -> str:
    redacted_assignments = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
        message,
    )
    return _SECRET_TOKEN_RE.sub("<redacted>", redacted_assignments)


def _public_warning_details(details: Mapping[str, object]) -> dict[str, str]:
    public_details: dict[str, str] = {}
    for key, value in details.items():
        normalized_key = str(key).strip()
        if not normalized_key or _SENSITIVE_WARNING_DETAIL_KEY_RE.search(normalized_key):
            continue
        key_tokens = _WARNING_DETAIL_KEY_TOKEN_RE.sub("_", normalized_key).strip("_")
        if not key_tokens:
            continue
        public_details[to_camel(key_tokens)] = _public_warning_message(str(value))
    return public_details


__all__ = [
    "empty_result_warning",
    "partial_result_warning",
    "provider_unavailable_warning",
    "runtime_warning",
    "truncated_result_warning",
    "unavailable_result_warning",
    "warning_from_provider_error",
    "warning_from_provider_failure",
    "warning_from_unhandled_provider_error",
]
