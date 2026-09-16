"""Closed deployment bindings for trusted plugin UI releases."""

import re
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from app.domain.tool_contracts import DIGEST, PLUGIN_ID, ToolContractModel
from app.schemas.common import CamelModel

MOUNT_KEY = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class PluginMount(ToolContractModel):
    mount_key: str = Field(pattern=MOUNT_KEY)
    plugin_id: str = Field(pattern=PLUGIN_ID)
    artifact_digest: str = Field(pattern=DIGEST)
    upstream: str

    @field_validator("upstream")
    @classmethod
    def safe_upstream(cls, value: str) -> str:
        # Deployment data also enters proxy configuration: prohibit directives,
        # credentials, variables and URI rewriting in this origin-only value.
        if not re.fullmatch(r"https?://[a-zA-Z0-9.-]+(?::[0-9]{1,5})?", value):
            raise ValueError("Plugin upstream must be an HTTP origin")
        parts = urlsplit(value)
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError("Plugin upstream port is invalid")
        return value


class PluginMountRegistry(ToolContractModel):
    version: Literal["signaldeck.pluginMounts/1"]
    mounts: tuple[PluginMount, ...]

    @model_validator(mode="after")
    def unique_bindings(self) -> Self:
        if len({item.mount_key for item in self.mounts}) != len(self.mounts):
            raise ValueError("Duplicate plugin mount key")
        if len({(item.plugin_id, item.artifact_digest) for item in self.mounts}) != len(
            self.mounts
        ):
            raise ValueError("A plugin release must have one mount")
        return self


class PluginPage(CamelModel):
    mount_key: str
    plugin_id: str
    artifact_digest: str
    title: str
    page_url: str
    enabled: bool
