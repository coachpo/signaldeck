from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_engine, get_session_factory
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.resource_limiter import PostgresResourceLimiter
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.schema_compatibility import main, schema_report
from app.infrastructure.tool_cache_store import PostgresToolCacheStore


def initialize_core_schema(database_url: str) -> None:
    session_factory = get_session_factory(database_url)
    PlatformStore(session_factory).initialize()
    ScheduleStore(session_factory).initialize()
    PostgresResourceLimiter(session_factory).initialize()
    PostgresToolCacheStore(session_factory).initialize()


def test_every_table_the_stores_create_is_checked(database_url: str) -> None:
    initialize_core_schema(database_url)

    report = schema_report(get_engine(database_url))

    assert report["compatible"] is True
    assert report["unknown_tables"] == []
    assert {item["status"] for item in report["tables"].values()} == {"ok"}
    assert "platform_runs" in report["tables"]
    assert "platform_read_tool_cache" in report["tables"]


def test_empty_database_only_needs_new_tables(database_url: str) -> None:
    report = schema_report(get_engine(database_url))

    assert report["compatible"] is True
    assert {item["status"] for item in report["tables"].values()} == {"created_on_start"}


def test_missing_model_column_is_incompatible(database_url: str) -> None:
    initialize_core_schema(database_url)
    with get_engine(database_url).begin() as connection:
        connection.execute(text("ALTER TABLE platform_runs DROP COLUMN error_code"))

    report = schema_report(get_engine(database_url))

    assert report["compatible"] is False
    assert report["tables"]["platform_runs"]["missing_columns"] == ["error_code"]


def test_unmapped_required_column_is_incompatible(database_url: str) -> None:
    initialize_core_schema(database_url)
    with get_engine(database_url).begin() as connection:
        connection.execute(text("ALTER TABLE platform_packages ADD COLUMN legacy text"))
        connection.execute(
            text("ALTER TABLE platform_packages ADD COLUMN retired text NOT NULL DEFAULT 'x'")
        )
        connection.execute(text("ALTER TABLE platform_packages ADD COLUMN required text"))
        connection.execute(text("ALTER TABLE platform_packages ALTER COLUMN required SET NOT NULL"))
        connection.execute(text("CREATE TABLE retired_side_table (id integer)"))

    report = schema_report(get_engine(database_url))

    assert report["compatible"] is False
    assert report["tables"]["platform_packages"]["unmapped_required_columns"] == ["required"]
    assert report["unknown_tables"] == ["retired_side_table"]


def test_cli_prints_names_and_reports_incompatibility(
    database_url: str,
    session_factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The session_factory fixture points DATABASE_URL, which the CLI reads, at this database.
    initialize_core_schema(database_url)
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["compatible"] is True

    with get_engine(database_url).begin() as connection:
        connection.execute(text("ALTER TABLE platform_runs DROP COLUMN error_code"))

    assert main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["compatible"] is False
    assert database_url not in output
