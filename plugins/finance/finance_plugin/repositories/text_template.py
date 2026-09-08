from __future__ import annotations

from finance_plugin.models.text_template import TextTemplate
from finance_plugin.repositories.base import BaseRepository
from sqlalchemy import select


class TextTemplateRepository(BaseRepository[TextTemplate]):
    model = TextTemplate

    def list_all(self) -> list[TextTemplate]:
        statement = select(self.model).order_by(self.model.created_at.desc())
        return self._list(statement)

    def get_by_name(self, name: str) -> TextTemplate | None:
        statement = select(self.model).where(self.model.name == name)
        return self._get_by_statement(statement)
