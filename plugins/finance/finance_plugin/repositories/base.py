from __future__ import annotations

from typing import ClassVar

from finance_plugin.models.base import Base
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select


class BaseRepository[ModelType: Base]:
    model: ClassVar[type[ModelType]]

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[ModelType]:
        return self._list(select(self.model))

    def get(self, entity_id: int) -> ModelType | None:
        return self.session.get(self.model, entity_id)

    def add(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        return instance

    def delete(self, instance: ModelType) -> None:
        self.session.delete(instance)

    def _list(self, statement: Select[tuple[ModelType]]) -> list[ModelType]:
        return list(self.session.scalars(statement))

    def _get_by_statement(self, statement: Select[tuple[ModelType]]) -> ModelType | None:
        return self.session.scalar(statement)
