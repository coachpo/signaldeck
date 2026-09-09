"""Batch source import HTTP contract."""

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.platform import DiagnosticRead, ManifestRequest


class ImportSource(ManifestRequest):
    name: str | None = Field(default=None, max_length=256)


class PackageImportRequest(CamelModel):
    sources: list[ImportSource] = Field(max_length=100)
    mode: Literal["missing_only", "update"] = "missing_only"


class ImportItemRead(CamelModel):
    name: str | None = None
    package_key: str | None = None
    status: Literal["created", "preserved", "updated", "error"]
    diagnostics: list[DiagnosticRead] = Field(default_factory=list)


class PackageImportRead(CamelModel):
    items: list[ImportItemRead]
