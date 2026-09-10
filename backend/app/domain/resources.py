"""Non-sensitive resource configuration captured by immutable run bindings."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.domain.model_diagnostics import ModelObservation
from app.schemas.common import CamelModel


def validate_public_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Use an HTTP URL without credentials, query or fragment")
    return value.rstrip("/")


class ModelConfiguration(CamelModel):
    name: str = Field(default="", max_length=200)
    base_url: str
    model_id: str = Field(min_length=1, max_length=200)
    api_style: Literal["chat_completions", "responses"] = "chat_completions"
    timeout_seconds: int = Field(default=60, ge=1, le=3600)

    @field_validator("base_url")
    @classmethod
    def public_endpoint(cls, value: str) -> str:
        return validate_public_url(value)


class ToolResourceConfiguration(CamelModel):
    name: str = Field(default="", max_length=200)
    plugin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*$")
    scope: dict[str, Any] = Field(default_factory=dict)
    max_concurrent_calls: int = Field(default=4, ge=1, le=1000)
    requests_per_second: float = Field(default=10, gt=0, le=10000)

    @field_validator("scope")
    @classmethod
    def non_sensitive_scope(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_credential_fields(value)
        return value


class ResolvedModelConfiguration(ModelConfiguration):
    """The selected model profile plus a server-owned credential reference."""

    credential_revision: str = Field(min_length=1)


class ResourceWrite(CamelModel):
    resource_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,119}$")
    kind: Literal["model", "tool"]
    config: dict[str, Any]
    credentials: dict[str, str] | None = None


class ResourceRead(CamelModel):
    model_observation: ModelObservation | None = None
    resource_id: str
    kind: Literal["model", "tool"]
    config: dict[str, Any]
    has_credentials: bool
    credential_revision: str


class ResolvedToolResourceConfiguration(ToolResourceConfiguration):
    """A server-owned credential identity reference, never a credential value."""

    credential_revision: str = Field(min_length=1)


def validate_resource(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    schema = ModelConfiguration if kind == "model" else ToolResourceConfiguration
    return schema.model_validate(config).model_dump(mode="json", by_alias=True)


def reject_credential_fields(value: Any) -> None:
    """Credential-bearing fields belong in the encrypted, write-only value map."""
    forbidden = {
        "credentials",
        "credential",
        "apikey",
        "password",
        "secret",
        "authorization",
        "cookie",
        "token",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "headers",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized in forbidden:
                raise ValueError("Resource scope cannot contain credential fields")
            reject_credential_fields(child)
    elif isinstance(value, list):
        for child in value:
            reject_credential_fields(child)
