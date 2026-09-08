"""Versioned credential encryption, independent of ORM and plugin models."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

ENCRYPTED_PAYLOAD_VERSION = 2


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().agent_platform_encryption_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "__encrypted__": True,
        "version": ENCRYPTED_PAYLOAD_VERSION,
        "ciphertext": _fernet().encrypt(json.dumps(payload).encode()).decode("ascii"),
    }


def decrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    if not payload.get("__encrypted__"):
        raise ValueError("Invalid encrypted JSON payload.")
    if payload.get("version") != ENCRYPTED_PAYLOAD_VERSION:
        raise ValueError("Unsupported encrypted JSON payload version.")
    try:
        plaintext = _fernet().decrypt(str(payload["ciphertext"]).encode("ascii"))
        result = json.loads(plaintext)
    except (InvalidToken, KeyError, ValueError, UnicodeError) as exc:
        raise ValueError("Invalid encrypted JSON payload.") from exc
    if not isinstance(result, dict):
        raise ValueError("Encrypted JSON payload must decode to an object.")
    return result
