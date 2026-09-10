"""Offline usage summaries scoped to an immutable run or an explicit local date."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.platform_dependencies import get_platform_store
from app.infrastructure.model_usage import read_model_usage
from app.infrastructure.platform_store import PlatformStore
from app.schemas.model_usage import ModelUsageRead

router = APIRouter(tags=["model-usage"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


@router.get("/runs/{run_id}/usage", response_model=ModelUsageRead)
def run_usage(run_id: str, store: Store) -> ModelUsageRead:
    return read_model_usage(store, run_id=run_id)


@router.get("/model-usage", response_model=ModelUsageRead)
def day_usage(
    store: Store, day: date = Query(alias="date"), timezone: str = Query(max_length=100)
) -> ModelUsageRead:
    return read_model_usage(store, day=day, timezone=timezone)
