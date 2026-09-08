"""Deployment-declared, non-sensitive connection choices."""

from typing import Any, Literal

from pydantic import Field, field_validator

from app.domain.resources import validate_resource
from app.schemas.common import CamelModel


class CredentialField(CamelModel):
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,99}$")
    label: str = Field(min_length=1, max_length=200)
    required: bool = False


class ConnectionPreset(CamelModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    resource_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,119}$")
    kind: Literal["model", "tool"]
    config: dict[str, Any]
    credential_fields: list[CredentialField] = Field(default_factory=list)

    @field_validator("config")
    @classmethod
    def safe_configuration(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        return validate_resource(info.data.get("kind", "tool"), value)


class ConnectionPresetList(CamelModel):
    items: list[ConnectionPreset] = Field(default_factory=list)
