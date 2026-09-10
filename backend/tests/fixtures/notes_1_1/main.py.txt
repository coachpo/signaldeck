"""A third, non-financial plugin: independently stored research notes."""

import os
from pathlib import Path

from notes_plugin.web import install_workspace, literal_match
from plugin_runtime.operations import Journal, OperationBase
from plugin_runtime.server import application, obj, release, tool
from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    collection: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)


def create_app(database_url=None):
    db_url = database_url or os.environ.get("PLUGIN_DATABASE_URL")
    if not db_url:
        raise ValueError("Notes requires its own PLUGIN_DATABASE_URL")
    engine = create_engine(db_url, hide_parameters=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    journal = Journal(sessions)
    note_schema = obj(
        {
            "id": {"type": "string"},
            "collection": {"type": "string"},
            "title": {"type": "string"},
            "text": {"type": "string"},
        },
        ("id", "collection", "title", "text"),
    )
    definitions = [
        tool(
            "example/notes",
            "create",
            obj(
                {
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "text": {"type": "string", "maxLength": 100000},
                },
                ("title", "text"),
            ),
            note_schema,
            "Store an immutable note, deduplicated by the operation identity.",
            write=True,
            result_links=[
                {
                    "version": "signaldeck.resultLink/1",
                    "key": "note",
                    "label": "打开笔记",
                    "path": "",
                    "query": {"noteId": "tool.output.id"},
                }
            ],
            resources=("notes-workspace",),
        ),
        tool(
            "example/notes",
            "search",
            obj(
                {
                    "query": {"type": "string", "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                }
            ),
            obj({"notes": {"type": "array", "items": note_schema}}, ("notes",)),
            "Search this plugin’s notes by title and content.",
            resources=("notes-workspace",),
        ),
    ]

    def execute(name, arguments, context):
        binding = context.get("resourceBindings", {}).get("notes-workspace", {})
        collection = binding.get("collection")
        if (
            not isinstance(collection, str)
            or not collection
            or len(collection) > 200
            or "notes-workspace" not in context.get("resourceGrants", [])
        ):
            raise ValueError("notes_collection_not_granted")
        if name == "example/notes/create":

            def effect(session):
                result = {
                    "id": context["operationId"],
                    "collection": collection,
                    "title": arguments["title"],
                    "text": arguments["text"],
                }
                session.add(Note(**result))
                session.flush()
                return result

            return journal.write(
                context["operationId"],
                name,
                arguments,
                effect,
                scope=context["resourceBindings"],
            )
        with sessions() as session:
            rows = session.scalars(
                select(Note)
                .where(Note.collection == collection)
                .where(literal_match(Note, arguments.get("query", "")))
                .order_by(Note.id)
                .limit(arguments.get("limit", 20))
            )
            return {
                "notes": [
                    {
                        "id": n.id,
                        "collection": n.collection,
                        "title": n.title,
                        "text": n.text,
                    }
                    for n in rows
                ]
            }

    def startup():
        Base.metadata.create_all(engine)
        OperationBase.metadata.create_all(engine)

    root = Path(__file__).resolve().parents[1]
    binding = release(
        "example/notes",
        (root / "VERSION").read_text().strip(),
        os.environ.get("PLUGIN_ENDPOINT", "http://notes:8000/mcp/"),
        definitions,
        [root, root.parent / "runtime"],
        page_url=os.environ.get("PLUGIN_PAGE_URL", "http://localhost:8093/"),
        config_schema=obj(
            {"collection": {"type": "string", "minLength": 1, "maxLength": 200}},
            ("collection",),
        ),
    )
    app = application(binding, execute, journal.query, startup=startup)
    install_workspace(app, sessions, Note)
    app.state.engine, app.state.execute, app.state.journal = engine, execute, journal
    return app
