from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import reset_settings_cache
from app.db.engine import get_engine, get_session_factory, reset_db_caches
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.schedule_store import ScheduleStore
from app.main import create_app

LOCAL_POSTGRES_CONTAINER = "signaldeck-target-test-postgres"
LOCAL_POSTGRES_IMAGE = "pgvector/pgvector:pg16"
LOCAL_POSTGRES_PORT = os.environ.get("LOCAL_POSTGRES_PORT", "")
LOCAL_POSTGRES_DATA = Path(
    os.environ.get(
        "SIGNALDECK_TEST_POSTGRES_DIR",
        str(Path(__file__).resolve().parents[1] / ".data" / "test-postgres"),
    )
).resolve()
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "signaldeck")


def _run_docker(args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        check=check,
        text=True,
    )


def _docker_container_running(container_name: str) -> bool:
    result = _run_docker(
        ["inspect", "-f", "{{.State.Running}}", container_name],
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _docker_container_exists(container_name: str) -> bool:
    return _run_docker(["inspect", container_name], check=False).returncode == 0


def _docker_container_port(container_name: str, container_port: int) -> str:
    result = _run_docker(["port", container_name, f"{container_port}/tcp"], check=False)
    if result.returncode != 0:
        return ""
    first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
    return first_line.rsplit(":", maxsplit=1)[-1] if first_line else ""


def _local_database_url(postgres_port: str) -> URL:
    return make_url(
        f"postgresql+psycopg://signaldeck:{POSTGRES_PASSWORD}@localhost:{postgres_port}/signaldeck"
    )


def _wait_for_start_local_database() -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not _docker_container_running(LOCAL_POSTGRES_CONTAINER):
            raise RuntimeError(
                f"Local PostgreSQL container {LOCAL_POSTGRES_CONTAINER} exited before ready."
            )
        result = _run_docker(
            [
                "exec",
                LOCAL_POSTGRES_CONTAINER,
                "pg_isready",
                "-U",
                "signaldeck",
                "-d",
                "signaldeck",
            ],
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("Local PostgreSQL did not become ready within 60s.")


def _ensure_start_local_database() -> URL:
    if _docker_container_running(LOCAL_POSTGRES_CONTAINER):
        postgres_port = _docker_container_port(LOCAL_POSTGRES_CONTAINER, 5432)
        if not postgres_port:
            raise RuntimeError(
                f"Could not resolve published PostgreSQL port for {LOCAL_POSTGRES_CONTAINER}."
            )
        if LOCAL_POSTGRES_PORT and LOCAL_POSTGRES_PORT != postgres_port:
            raise RuntimeError(
                f"Local PostgreSQL container {LOCAL_POSTGRES_CONTAINER} is already running "
                f"on port {postgres_port}, not LOCAL_POSTGRES_PORT={LOCAL_POSTGRES_PORT}."
            )
        _wait_for_start_local_database()
        return _local_database_url(postgres_port)

    if LOCAL_POSTGRES_PORT and not LOCAL_POSTGRES_PORT.isdecimal():
        raise RuntimeError("LOCAL_POSTGRES_PORT must be a numeric TCP port.")

    if _docker_container_exists(LOCAL_POSTGRES_CONTAINER):
        existing_postgres_port = _docker_container_port(LOCAL_POSTGRES_CONTAINER, 5432)
        if not LOCAL_POSTGRES_PORT and existing_postgres_port:
            _run_docker(["rm", LOCAL_POSTGRES_CONTAINER], check=True)
        elif (
            LOCAL_POSTGRES_PORT
            and existing_postgres_port
            and LOCAL_POSTGRES_PORT != existing_postgres_port
        ):
            _run_docker(["rm", LOCAL_POSTGRES_CONTAINER], check=True)

    if _docker_container_exists(LOCAL_POSTGRES_CONTAINER):
        _run_docker(["start", LOCAL_POSTGRES_CONTAINER], check=True)
    else:
        postgres_publish_port = (
            f"127.0.0.1:{LOCAL_POSTGRES_PORT}:5432" if LOCAL_POSTGRES_PORT else "127.0.0.1::5432"
        )
        LOCAL_POSTGRES_DATA.mkdir(parents=True, exist_ok=True)
        _run_docker(
            [
                "run",
                "-d",
                "--name",
                LOCAL_POSTGRES_CONTAINER,
                "--label",
                "io.signaldeck.support=local-demo-only",
                "--label",
                "io.signaldeck.production-artifact=false",
                "--label",
                "io.signaldeck.test-resource=sd-target-001",
                "-e",
                "POSTGRES_DB=signaldeck",
                "-e",
                "POSTGRES_USER=signaldeck",
                "-e",
                f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
                "-p",
                postgres_publish_port,
                "-v",
                f"{LOCAL_POSTGRES_DATA}:/var/lib/postgresql/data",
                LOCAL_POSTGRES_IMAGE,
            ],
            check=True,
        )
    _wait_for_start_local_database()
    postgres_port = _docker_container_port(LOCAL_POSTGRES_CONTAINER, 5432)
    if not postgres_port:
        raise RuntimeError(
            f"Could not resolve published PostgreSQL port for {LOCAL_POSTGRES_CONTAINER}."
        )
    return _local_database_url(postgres_port)


def _get_base_database_url() -> URL:
    raw_database_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    database_url = (
        make_url(raw_database_url) if raw_database_url else _ensure_start_local_database()
    )
    if database_url.get_backend_name() not in {"postgresql", "postgres"}:
        raise RuntimeError("Tests require a PostgreSQL DATABASE_URL or TEST_DATABASE_URL.")
    return database_url


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@pytest.fixture(autouse=True)
def _isolate_api_token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("SIGNALDECK_API_TOKEN", raising=False)
    reset_settings_cache()

    yield

    reset_settings_cache()


@pytest.fixture()
def database_url() -> Iterator[str]:
    base_database_url = _get_base_database_url()
    admin_database_url = base_database_url.set(database="postgres")
    database_name = f"signaldeck_test_{uuid4().hex}"
    resolved_database_url = base_database_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    admin_engine = create_engine(admin_database_url, isolation_level="AUTOCOMMIT", future=True)

    with admin_engine.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {_quote_identifier(database_name)}"))

    try:
        yield resolved_database_url
    finally:
        get_engine(resolved_database_url).dispose()
        reset_db_caches()
        reset_settings_cache()
        with admin_engine.connect() as connection:
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {_quote_identifier(database_name)} WITH (FORCE)")
            )
        admin_engine.dispose()


@pytest.fixture()
def session_factory(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    reset_settings_cache()
    reset_db_caches()
    yield get_session_factory(database_url)

    get_engine(database_url).dispose()
    reset_db_caches()
    reset_settings_cache()


@pytest.fixture()
def app(session_factory: sessionmaker[Session]) -> FastAPI:
    PlatformStore(session_factory).initialize()
    ScheduleStore(session_factory).initialize()
    return create_app(init_database=False)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
