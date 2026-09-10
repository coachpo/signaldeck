"""Read-only operator workspace for the independently owned Notes database."""

from pathlib import Path

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError


def literal_match(note, query):
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%" + escaped + "%"
    return note.title.ilike(pattern, escape="\\") | note.text.ilike(
        pattern, escape="\\"
    )


def source_filter(note, provenance, include_derived):
    return (
        True
        if include_derived
        else ~select(provenance.note_id)
        .where(provenance.note_id == note.id, provenance.source_kind == "derived")
        .exists()
    )


def project(note, session, provenance):
    metadata = session.get(provenance, note.id)
    return {
        **{key: getattr(note, key) for key in ("id", "collection", "title", "text")},
        "sourceKind": metadata.source_kind if metadata else "unclassified",
        "sourceNoteIds": metadata.source_ids if metadata else [],
    }


def install_workspace(app, sessions, note, provenance):
    web = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web), name="notes-assets")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(
            status_code=422,
            content={
                "code": "notes_invalid_request",
                "message": "笔记查询参数无效。",
                "details": [],
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request, error):
        return JSONResponse(
            status_code=503,
            content={
                "code": "notes_unavailable",
                "message": "笔记暂时无法读取，请稍后重试。",
                "details": [],
            },
        )

    @app.get("/", include_in_schema=False)
    def workspace():
        return FileResponse(web / "index.html")

    @app.get("/api/collections")
    def collections():
        with sessions() as session:
            rows = session.execute(
                select(note.collection, func.count())
                .group_by(note.collection)
                .order_by(note.collection)
            )
            return {
                "collections": [{"name": name, "count": count} for name, count in rows]
            }

    @app.get("/api/notes")
    def notes(
        collection: str = Query(min_length=1, max_length=200),
        query: str = Query(default="", max_length=200),
        includeDerived: bool = Query(default=True),
        after: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=20, ge=1, le=50),
    ):
        statement = select(note).where(
            note.collection == collection,
            literal_match(note, query),
            source_filter(note, provenance, includeDerived),
        )
        if after is not None:
            statement = statement.where(note.id > after)
        with sessions() as session:
            rows = list(session.scalars(statement.order_by(note.id).limit(limit + 1)))
            return {
                "notes": [project(row, session, provenance) for row in rows[:limit]],
                "nextCursor": rows[limit - 1].id if len(rows) > limit else None,
            }

    @app.get("/api/note")
    def detail(id: str = Query(min_length=1, max_length=200)):
        with sessions() as session:
            row = session.get(note, id)
            if row is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "code": "note_not_found",
                        "message": "找不到这条笔记。",
                        "details": [],
                    },
                )
            return project(row, session, provenance)
