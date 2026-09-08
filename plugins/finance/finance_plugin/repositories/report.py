from __future__ import annotations

from finance_plugin.models.report import Report
from finance_plugin.repositories.base import BaseRepository
from sqlalchemy import or_, select


class ReportRepository(BaseRepository[Report]):
    model = Report

    def list_all(
        self,
        *,
        q: str | None = None,
        sort: str = "newest",
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Report]:
        statement = select(self.model)

        if q is not None:
            statement = statement.where(
                or_(
                    self.model.name.icontains(q, autoescape=True),
                    self.model.content.icontains(q, autoescape=True),
                    self.model.slug.icontains(q, autoescape=True),
                )
            )
        if ticker is not None:
            statement = statement.where(
                self.model.metadata_.contains({"analysis": {"ticker": ticker}})
            )
        if tag is not None:
            statement = statement.where(self.model.metadata_.contains({"tags": [tag]}))
        if review_type is not None:
            statement = statement.where(
                self.model.metadata_.contains({"analysis": {"reviewType": review_type}})
            )
        if source is not None:
            statement = statement.where(self.model.source == source)

        if sort == "name":
            statement = statement.order_by(self.model.name.asc(), self.model.id.asc())
        elif sort == "oldest":
            statement = statement.order_by(self.model.created_at.asc(), self.model.id.asc())
        else:
            statement = statement.order_by(self.model.created_at.desc(), self.model.id.desc())

        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        return self._list(statement)

    def get_by_name(self, name: str) -> Report | None:
        statement = select(self.model).where(self.model.name == name)
        return self._get_by_statement(statement)

    def get_by_slug(self, slug: str) -> Report | None:
        statement = select(self.model).where(self.model.slug == slug)
        return self._get_by_statement(statement)
