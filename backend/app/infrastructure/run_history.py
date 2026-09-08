"""Database-wide run filtering, stable ordering and pagination."""

from datetime import datetime
from typing import Literal

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.platform_models import EvidenceRow, RunRow


def query_history(
    sessions: sessionmaker[Session],
    *,
    q: str | None = None,
    group: Literal["active", "attention"] | None = None,
    status: str | None = None,
    package_key: str | None = None,
    workflow_key: str | None = None,
    origin: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Literal["created_desc", "created_asc", "title_asc", "title_desc"] = "created_desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RunRow], int, set[str]]:
    title = func.coalesce(
        *[
            case(
                (
                    func.jsonb_typeof(RunRow.spec["parameters"][key]) == "string",
                    func.nullif(
                        func.substr(
                            func.regexp_replace(
                                RunRow.spec["parameters"][key].astext, r"^\s+|\s+$", "", "g"
                            ),
                            1,
                            300,
                        ),
                        "",
                    ),
                ),
                else_=None,
            )
            for key in ("title", "question")
        ],
        func.nullif(
            RunRow.spec["definition"]["workflows"]
            .op("->")(RunRow.spec["workflowKey"].astext)
            .op("->>")("name"),
            "",
        ),
        RunRow.spec["definition"]["metadata"]["name"].astext,
        RunRow.spec["workflowKey"].astext,
    )
    query = select(RunRow)
    if group == "active":
        query = query.where(RunRow.status.in_(("queued", "running")))
    elif group == "attention":
        unresolved = (
            select(EvidenceRow.id)
            .where(
                EvidenceRow.run_id == RunRow.id,
                EvidenceRow.payload["status"].astext == "unknown",
                EvidenceRow.payload["kind"].astext != "attempt",
            )
            .exists()
        )
        query = query.where(or_(RunRow.status == "failed", unresolved))
    if q:
        query = query.where(
            or_(
                title.contains(q, autoescape=True),
                RunRow.id.contains(q, autoescape=True),
                RunRow.spec["packageKey"].astext.contains(q, autoescape=True),
                RunRow.spec["workflowKey"].astext.contains(q, autoescape=True),
                cast(RunRow.output, String).contains(q, autoescape=True),
            )
        )
    for expression, value in (
        (RunRow.status, status),
        (RunRow.spec["packageKey"].astext, package_key),
        (RunRow.spec["workflowKey"].astext, workflow_key),
        (RunRow.spec["origin"]["kind"].astext, origin),
    ):
        if value is not None:
            query = query.where(expression == value)
    if created_from is not None:
        query = query.where(RunRow.created_at >= created_from)
    if created_to is not None:
        query = query.where(RunRow.created_at <= created_to)
    ordering = {
        "created_desc": RunRow.created_at.desc(),
        "created_asc": RunRow.created_at.asc(),
        "title_asc": title.asc(),
        "title_desc": title.desc(),
    }[sort]
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(
            session.scalars(query.order_by(ordering, RunRow.id).limit(limit).offset(offset))
        )
        unknown_ids = (
            set(
                session.scalars(
                    select(EvidenceRow.run_id).where(
                        EvidenceRow.run_id.in_([row.id for row in rows]),
                        EvidenceRow.payload["status"].astext == "unknown",
                        EvidenceRow.payload["kind"].astext != "attempt",
                    )
                )
            )
            if rows
            else set()
        )
        return rows, total, unknown_ids
