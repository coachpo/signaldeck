from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)  # noqa: UP017
    return value.astimezone(timezone.utc)  # noqa: UP017


def decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


def format_decimal(value: Decimal, *, places: int) -> str:
    quantizer = Decimal("1") if places == 0 else Decimal(f"1.{'0' * places}")
    return format(value.quantize(quantizer, rounding=ROUND_HALF_UP), f".{places}f")


def format_nullable_decimal(value: Decimal | None, *, places: int = 2) -> str | None:
    if value is None:
        return None
    return format_decimal(value, places=places)


def parse_decimal_string(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Decimal value is required")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Invalid decimal value") from exc
    raise ValueError("Decimal values must be strings")


def normalize_symbol(value: str) -> str:
    return value.strip().upper()


def normalize_currency(value: str) -> str:
    return value.strip().upper()
