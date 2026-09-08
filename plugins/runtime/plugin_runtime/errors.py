from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import cast

from fastapi import status
from fastapi.exceptions import RequestValidationError

type BrowserSafeErrorDetailValue = str | int | float | bool | None
type BrowserSafeErrorDetail = dict[str, BrowserSafeErrorDetailValue]

_DETAIL_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_UNSAFE_DETAIL_KEY_PARTS = (
    "apikey",
    "authorization",
    "credential",
    "exception",
    "header",
    "internal",
    "password",
    "secret",
    "stack",
    "token",
    "traceback",
)
_MAX_DETAIL_STRING_LENGTH = 500


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code: int = status_code
        self.code: str = code
        self.message: str = message
        self.details: list[BrowserSafeErrorDetail] = browser_safe_error_details(details)


def browser_safe_error_details(details: object) -> list[BrowserSafeErrorDetail]:
    if not isinstance(details, Sequence) or isinstance(details, str | bytes | bytearray):
        return []

    safe_details: list[BrowserSafeErrorDetail] = []
    for detail in details:
        if not isinstance(detail, Mapping):
            continue

        safe_detail: BrowserSafeErrorDetail = {}
        detail_mapping = cast(Mapping[object, object], detail)
        for raw_key, raw_value in detail_mapping.items():
            if not isinstance(raw_key, str) or not _browser_safe_detail_key(raw_key):
                continue
            is_safe_value, safe_value = _browser_safe_detail_value(raw_value)
            if not is_safe_value:
                continue
            safe_detail[raw_key] = safe_value

        if safe_detail:
            safe_details.append(safe_detail)

    return safe_details


def _browser_safe_detail_key(key: str) -> bool:
    if _DETAIL_KEY_RE.fullmatch(key) is None:
        return False

    normalized_key = re.sub(r"[^A-Za-z0-9]", "", key).lower()
    return not any(part in normalized_key for part in _UNSAFE_DETAIL_KEY_PARTS)


def _browser_safe_detail_value(value: object) -> tuple[bool, BrowserSafeErrorDetailValue]:
    if value is None or isinstance(value, bool | int):
        return True, value
    if isinstance(value, float):
        return (True, value) if math.isfinite(value) else (False, None)
    if isinstance(value, str):
        if len(value) <= _MAX_DETAIL_STRING_LENGTH:
            return True, value
        return True, f"{value[:_MAX_DETAIL_STRING_LENGTH - 3]}..."
    return False, None


def not_found_error(resource_name: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=f"{resource_name} not found",
    )


def business_rule_error(
    code: str, message: str, details: Sequence[Mapping[str, object]] | None = None
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=code,
        message=message,
        details=details,
    )


def validation_error(
    message: str, details: Sequence[Mapping[str, object]] | None = None
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message=message,
        details=details,
    )


def malformed_file_error(
    message: str, details: Sequence[Mapping[str, object]] | None = None
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="malformed_file",
        message=message,
        details=details,
    )


def request_validation_to_details(exc: RequestValidationError) -> list[BrowserSafeErrorDetail]:
    details: list[BrowserSafeErrorDetail] = []
    validation_errors = cast(Sequence[Mapping[str, object]], exc.errors())
    for error in validation_errors:
        location = error.get("loc", ())
        location_parts = (
            location
            if isinstance(location, Sequence) and not isinstance(location, str | bytes | bytearray)
            else ()
        )
        field_parts = [
            str(part) for part in location_parts if part not in {"body", "query", "path"}
        ]
        field = ".".join(field_parts) if field_parts else "request"
        issue = error.get("msg", "Invalid value")
        details.append({"field": field, "issue": str(issue)})
    return details
