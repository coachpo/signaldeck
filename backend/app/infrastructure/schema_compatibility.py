"""Compare this release's Core table models with an existing PostgreSQL schema.

`create_all` creates missing tables but never alters an existing one. A model column
absent from a live table, or a required live column the models no longer write,
would therefore only fail at runtime after an upgrade. Deployments run this module
from the new image against the live database before switching:

    python -m app.infrastructure.schema_compatibility

It prints table and column names only and exits 1 when the schema is incompatible.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from collections.abc import Iterator
from typing import Any

from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

import app.infrastructure
from app.db.engine import get_engine


def _declarative_bases(root: type[DeclarativeBase]) -> Iterator[type[DeclarativeBase]]:
    for subclass in root.__subclasses__():
        if "__tablename__" not in subclass.__dict__:
            yield subclass
        yield from _declarative_bases(subclass)


def core_metadata() -> list[MetaData]:
    """Every table the Core stores create, including side tables registered on import."""
    for module in pkgutil.iter_modules(app.infrastructure.__path__):
        importlib.import_module(f"{app.infrastructure.__name__}.{module.name}")
    unique = {id(base.metadata): base.metadata for base in _declarative_bases(DeclarativeBase)}
    return list(unique.values())


def schema_report(engine: Engine) -> dict[str, Any]:
    live = inspect(engine)
    existing = set(live.get_table_names())
    tables: dict[str, dict[str, Any]] = {}
    for metadata in core_metadata():
        for table in metadata.sorted_tables:
            if table.name not in existing:
                tables[table.name] = {"status": "created_on_start"}
                continue
            live_columns = {column["name"]: column for column in live.get_columns(table.name)}
            model_columns = {column.name for column in table.columns}
            missing = sorted(model_columns - set(live_columns))
            unmapped_required = sorted(
                name
                for name, column in live_columns.items()
                if name not in model_columns
                and not column["nullable"]
                and column.get("default") is None
                and not column.get("identity")
                and not column.get("computed")
            )
            tables[table.name] = {
                "status": "incompatible" if missing or unmapped_required else "ok",
                "missing_columns": missing,
                "unmapped_required_columns": unmapped_required,
            }
    return {
        "compatible": all(item["status"] != "incompatible" for item in tables.values()),
        "tables": tables,
        "unknown_tables": sorted(existing - set(tables)),
    }


def main() -> int:
    report = schema_report(get_engine())
    print(json.dumps(report, sort_keys=True))
    return 0 if report["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
