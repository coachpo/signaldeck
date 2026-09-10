"""Personal annotations are separate from immutable execution records."""

from datetime import datetime

from pydantic import Field, model_validator

from app.schemas.common import CamelModel


class ResultMetadataRead(CamelModel):
    run_id: str
    revision: int = 0
    is_favorite: bool = False
    is_read: bool = False
    note: str = ""
    updated_at: datetime | None = None


class ResultMetadataPatch(CamelModel):
    expected_revision: int = Field(ge=0)
    is_favorite: bool | None = None
    is_read: bool | None = None
    note: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def require_changes(self) -> "ResultMetadataPatch":
        changes = self.model_fields_set - {"expected_revision"}
        if not changes or any(getattr(self, field) is None for field in changes):
            raise ValueError("Supply at least one non-null annotation field")
        return self
