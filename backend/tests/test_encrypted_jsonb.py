from __future__ import annotations

import json
from typing import cast

import pytest
from sqlalchemy.engine import Dialect

from app.core.config import reset_settings_cache
from app.infrastructure.secret_storage import EncryptedJSONB

_DIALECT = cast(Dialect, object())


@pytest.fixture(autouse=True)
def reset_settings_cache_after_test() -> None:
    yield
    reset_settings_cache()


def set_encryption_key(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", value)
    reset_settings_cache()


def test_encrypted_jsonb_round_trips_with_version_two_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_key(monkeypatch, "round-trip-key")
    column = EncryptedJSONB()
    payload = {"apiKey": "secret-value", "metadata": {"purpose": "round-trip"}}

    stored = column.process_bind_param(payload, _DIALECT)

    assert stored["__encrypted__"] is True
    assert stored["version"] == 2
    assert column.process_result_value(stored, _DIALECT) == payload


def test_encrypted_jsonb_wrong_key_decrypt_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_key(monkeypatch, "first-key")
    column = EncryptedJSONB()
    stored = column.process_bind_param({"apiKey": "secret-value"}, _DIALECT)

    set_encryption_key(monkeypatch, "second-key")

    with pytest.raises(ValueError, match="Invalid encrypted JSON payload."):
        column.process_result_value(stored, _DIALECT)


def test_encrypted_jsonb_ciphertext_does_not_contain_plaintext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_encryption_key(monkeypatch, "ciphertext-key")
    column = EncryptedJSONB()
    secret_value = "plaintext-secret-value"

    stored = column.process_bind_param({"apiKey": secret_value}, _DIALECT)

    rendered = json.dumps(stored)
    assert secret_value not in rendered
    assert "apiKey" not in rendered
