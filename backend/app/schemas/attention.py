"""Current execution updates and explicit per-update read receipts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.domain.model_diagnostics import ModelErrorCategory
from app.schemas.common import CamelModel


class AttentionItem(CamelModel):
    id: str
    kind: Literal["run", "fire"]
    title: str
    status: str
    run_id: str | None = None
    schedule_id: str | None = None
    trigger_id: str | None = None
    occurred_at: datetime
    has_unknown_effects: bool = False
    has_unknown_results: bool = False
    error_code: str | None = None
    error_category: ModelErrorCategory | None = None
    is_read: bool = False
    revision: int = 0


class AttentionList(CamelModel):
    items: list[AttentionItem]
    total: int
    limit: int
    offset: int
    snapshot_at: datetime
    history_scope: Literal["all_current_records"] = "all_current_records"


class AttentionReadPatch(CamelModel):
    expected_revision: int = Field(ge=0)
    is_read: bool
