"""Encrypted PostgreSQL credential values, resolved only by I/O adapters."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.encryption import decrypt_payload, encrypt_payload


class EncryptedJSONB(TypeDecorator[dict[str, Any]]):
    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: dict[str, Any] | None, dialect: Dialect) -> dict[str, Any]:
        del dialect
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("Encrypted JSON payloads must be stored as JSON objects.")
        return encrypt_payload(value)

    def process_result_value(
        self, value: dict[str, Any] | None, dialect: Dialect
    ) -> dict[str, Any]:
        del dialect
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("Stored encrypted JSON payload rows must decode to JSON objects.")
        return decrypt_payload(value)
