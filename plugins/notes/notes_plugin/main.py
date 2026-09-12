"""A third, non-financial plugin: independently stored research notes."""

import os
from pathlib import Path

from notes_plugin.web import install_workspace, literal_match, project, source_filter
from plugin_runtime.operations import Journal, OperationBase
from plugin_runtime.server import application, obj, release, tool
from plugin_runtime.web import mount_shared_ui
from sqlalchemy import JSON, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    collection: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)


class NoteProvenance(Base):
    __tablename__ = "note_provenance"
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id"), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(20))
    source_ids: Mapped[list[str]] = mapped_column(JSON)


def create_app(database_url=None):
    db_url = database_url or os.environ.get("PLUGIN_DATABASE_URL")
    if not db_url:
        raise ValueError("Notes requires its own PLUGIN_DATABASE_URL")
    engine = create_engine(db_url, hide_parameters=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    journal = Journal(sessions)
    source_ids_schema = {
        "type": "array",
        "items": {"type": "string", "minLength": 1, "maxLength": 200},
        "maxItems": 50,
        "uniqueItems": True,
    }
    note_schema = obj(
        {
            "id": {"type": "string"},
            "collection": {"type": "string"},
            "title": {"type": "string"},
            "text": {"type": "string"},
            "sourceKind": {
                "type": "string",
                "enum": ["original", "derived", "unclassified"],
            },
            "sourceNoteIds": source_ids_schema,
        },
        ("id", "collection", "title", "text", "sourceKind", "sourceNoteIds"),
    )
    definitions = [
        tool(
            "example/notes",
            "create",
            obj(
                {
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "text": {"type": "string", "maxLength": 100000},
                    "sourceKind": {"type": "string", "enum": ["original", "derived"]},
                    "sourceNoteIds": source_ids_schema,
                },
                ("title", "text"),
            ),
            note_schema,
            (
                "Store an immutable note with explicit provenance and confirmed same-collection "
                "source IDs. Omitted sourceKind remains unclassified. Original notes cannot cite "
                "sources. Deduplicated by operation identity."
            ),
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
                    "includeDerived": {"type": "boolean"},
                }
            ),
            obj(
                {
                    "notes": {"type": "array", "items": note_schema},
                    "sourceNoteIds": source_ids_schema,
                },
                ("notes", "sourceNoteIds"),
            ),
            (
                "Search this collection by literal title/content. includeDerived defaults to true; "
                "false excludes explicitly derived notes and retains historical unclassified "
                "records. sourceNoteIds exactly identifies returned notes."
            ),
            resources=("notes-workspace",),
        ),
    ]

    definitions[0]["inputSchema"]["title"] = "保存笔记"
    definitions[1]["inputSchema"]["title"] = "查找笔记"
    field_titles = {
        "title": "笔记标题",
        "text": "笔记正文",
        "sourceKind": "资料类型",
        "sourceNoteIds": "引用的原始笔记",
        "query": "查找文字",
        "limit": "最多返回条数",
        "includeDerived": "包含整理结果",
    }
    for definition in definitions:
        for name, schema in definition["inputSchema"]["properties"].items():
            schema["title"] = field_titles[name]

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
                kind = arguments.get("sourceKind", "unclassified")
                sources = arguments.get("sourceNoteIds", [])
                if kind not in {"original", "derived", "unclassified"} or (
                    sources and kind != "derived"
                ):
                    raise ValueError("notes_invalid_provenance")
                if len(sources) > 50 or len(set(sources)) != len(sources):
                    raise ValueError("notes_invalid_sources")
                confirmed = set(
                    session.scalars(
                        select(Note.id).where(Note.collection == collection, Note.id.in_(sources))
                    )
                )
                if confirmed != set(sources):
                    raise ValueError("notes_sources_not_available")
                session.add(Note(**result))
                session.flush()
                session.add(
                    NoteProvenance(note_id=result["id"], source_kind=kind, source_ids=sources)
                )
                session.flush()
                return {**result, "sourceKind": kind, "sourceNoteIds": sources}

            return journal.write(
                context["operationId"],
                name,
                arguments,
                effect,
                scope=context["resourceBindings"],
            )
        with sessions() as session:
            rows = list(
                session.scalars(
                    select(Note)
                    .where(Note.collection == collection)
                    .where(literal_match(Note, arguments.get("query", "")))
                    .where(
                        source_filter(Note, NoteProvenance, arguments.get("includeDerived", True))
                    )
                    .order_by(Note.id)
                    .limit(arguments.get("limit", 20))
                )
            )
            return {
                "notes": [project(n, session, NoteProvenance) for n in rows],
                "sourceNoteIds": [n.id for n in rows],
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
        config_schema={
            "title": "笔记服务",
            **obj(
                {
                    "collection": {
                        "title": "笔记集合",
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                    }
                },
                ("collection",),
            ),
        },
    )
    app = application(binding, execute, journal.query, startup=startup)
    mount_shared_ui(app)
    install_workspace(app, sessions, Note, NoteProvenance)
    app.state.engine, app.state.execute, app.state.journal = engine, execute, journal
    return app
